from __future__ import annotations

import os
from collections import defaultdict, deque
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, execute_values


def _connect(url: str):
    return psycopg2.connect(url, sslmode="require" if "supabase.com" in url else "prefer")


def _tables(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        return [r[0] for r in cur.fetchall() if r[0] != "alembic_version"]


def _columns(conn, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
        """, (table,))
        return [r[0] for r in cur.fetchall()]


def _column_types(conn, table: str) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
        """, (table,))
        return {name: data_type for name, data_type in cur.fetchall()}


def _dependencies(conn) -> dict[str, set[str]]:
    deps: dict[str, set[str]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tc.table_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name=tc.constraint_name
             AND ccu.constraint_schema=tc.constraint_schema
            WHERE tc.constraint_type='FOREIGN KEY'
              AND tc.table_schema='public'
        """)
        for child, parent in cur.fetchall():
            if child != parent and child != "alembic_version" and parent != "alembic_version":
                deps[child].add(parent)
    return deps


def _topological_order(tables: list[str], deps: dict[str, set[str]]) -> list[str]:
    indegree = {t: 0 for t in tables}
    children: dict[str, set[str]] = defaultdict(set)
    for child, parents in deps.items():
        for parent in parents:
            if parent in indegree:
                indegree[child] += 1
                children[parent].add(child)

    queue = deque(sorted(t for t, d in indegree.items() if d == 0))
    ordered: list[str] = []
    while queue:
        parent = queue.popleft()
        ordered.append(parent)
        for child in sorted(children[parent]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered) != len(tables):
        remaining = sorted(set(tables) - set(ordered))
        raise RuntimeError(f"Foreign-key dependency cycle detected: {remaining}")
    return ordered


def _count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
        return int(cur.fetchone()[0])


def _copy_table(source, target, table: str, batch_size: int = 1000) -> tuple[int, int]:
    columns = _columns(source, table)
    if not columns:
        return 0, 0
    column_types = _column_types(source, table)

    with source.cursor(name=f"primhora_migrate_{table}") as src:
        src.itersize = batch_size
        src.execute(
            sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.Identifier(table),
            )
        )
        inserted = 0
        placeholders = "(" + ",".join(["%s"] * len(columns)) + ")"
        insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT DO NOTHING").format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
        ).as_string(target)

        with target.cursor() as dst:
            while True:
                rows = src.fetchmany(batch_size)
                if not rows:
                    break
                adapted_rows = [
                    tuple(Json(value) if column_types[column] in {"json", "jsonb"} and value is not None else value
                          for column, value in zip(columns, row))
                    for row in rows
                ]
                execute_values(dst, insert_sql, adapted_rows, template=placeholders, page_size=batch_size)
                target.commit()
                inserted += len(rows)

    return inserted, _count(target, table)


def _sync_sequences(target) -> None:
    with target.cursor() as cur:
        cur.execute("""
            SELECT
              n.nspname,
              c.relname AS table_name,
              a.attname AS column_name,
              seq.relname AS sequence_name
            FROM pg_class seq
            JOIN pg_depend d ON d.objid = seq.oid AND d.deptype = 'a'
            JOIN pg_class c ON c.oid = d.refobjid
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE seq.relkind='S' AND n.nspname='public'
        """)
        sequences = cur.fetchall()

    for schema, table, column, sequence in sequences:
        with target.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT MAX({}) FROM {}.{}").format(
                    sql.Identifier(column),
                    sql.Identifier(schema),
                    sql.Identifier(table),
                )
            )
            maximum = cur.fetchone()[0]
            if maximum is None:
                cur.execute(
                    "SELECT setval(%s::regclass, 1, false)",
                    (f"{schema}.{sequence}",),
                )
            else:
                cur.execute(
                    "SELECT setval(%s::regclass, %s, true)",
                    (f"{schema}.{sequence}", maximum),
                )
        target.commit()


def run() -> dict[str, Any]:
    source_url = os.environ.get("DATABASE_URL")
    target_url = os.environ.get("PRIMHORA_MIGRATION_TARGET_URL")
    if not source_url or not target_url:
        raise RuntimeError("DATABASE_URL and PRIMHORA_MIGRATION_TARGET_URL are required")

    source = _connect(source_url)
    target = _connect(target_url)
    try:
        tables = _tables(source)
        deps = _dependencies(source)
        ordered = _topological_order(tables, deps)

        report: dict[str, Any] = {"tables": {}, "order": ordered}
        for table in ordered:
            source_count = _count(source, table)
            target_before = _count(target, table)
            copied, target_after = _copy_table(source, target, table)
            report["tables"][table] = {
                "source": source_count,
                "target_before": target_before,
                "rows_scanned": copied,
                "target_after": target_after,
                "match": source_count == target_after,
            }
            if source_count != target_after:
                raise RuntimeError(
                    f"Row-count verification failed for {table}: source={source_count}, target={target_after}"
                )

        _sync_sequences(target)

        with target.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

        report["status"] = "verified"
        return report
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    result = run()
    total = sum(v["source"] for v in result["tables"].values())
    print(f"PRIMHORA Supabase migration verified: {len(result['tables'])} tables, {total} rows")
    for table, data in result["tables"].items():
        print(f"  {table}: {data['source']} -> {data['target_after']}")