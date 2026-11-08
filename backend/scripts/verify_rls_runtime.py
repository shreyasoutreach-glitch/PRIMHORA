"""Exercise PostgreSQL RLS as the restricted production runtime role.

Run after Alembic has applied the RLS migration:
    python scripts/verify_rls_runtime.py

All test rows are created in one transaction and rolled back. This is intended
for CI/local Postgres, not the live production database.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings


def main() -> None:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET ROLE primhora_runtime"))
            role = connection.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).mappings().one()
            assert role["current_user"] == "primhora_runtime"
            assert role["rolsuper"] is False
            assert role["rolbypassrls"] is False

            # The role must not own tenant tables and every tenant-keyed
            # public table must have RLS enabled plus the expected policy.
            policy_check = connection.execute(
                text(
                    """
                    WITH tenant_tables AS (
                        SELECT DISTINCT c.table_name
                        FROM information_schema.columns c
                        JOIN information_schema.tables t
                          ON t.table_schema = c.table_schema
                         AND t.table_name = c.table_name
                        WHERE c.table_schema = 'public'
                          AND c.column_name = 'tenant_id'
                          AND t.table_type = 'BASE TABLE'
                    ),
                    secured AS (
                        SELECT tablename
                        FROM pg_policies
                        WHERE schemaname = 'public'
                          AND policyname = 'primhora_tenant_isolation'
                    )
                    SELECT
                        (SELECT count(*) FROM tenant_tables) AS tenant_table_count,
                        (SELECT count(*) FROM tenant_tables tt
                         JOIN secured s ON s.tablename = tt.table_name) AS policy_count,
                        (SELECT count(*) FROM tenant_tables tt
                         JOIN pg_class c ON c.relname = tt.table_name
                         JOIN pg_namespace n ON n.oid = c.relnamespace
                         WHERE n.nspname = 'public' AND c.relrowsecurity) AS rls_count,
                        (SELECT count(*) FROM tenant_tables tt
                         JOIN pg_class c ON c.relname = tt.table_name
                         JOIN pg_namespace n ON n.oid = c.relnamespace
                         WHERE n.nspname = 'public'
                           AND pg_get_userbyid(c.relowner) = current_user) AS owned_count
                    """
                )
            ).mappings().one()
            assert policy_check["tenant_table_count"] == policy_check["policy_count"]
            assert policy_check["tenant_table_count"] == policy_check["rls_count"]
            assert policy_check["owned_count"] == 0

            connection.execute(
                text(
                    "SELECT set_config('app.tenant_id', '', true), "
                    "set_config('app.oidc_subject', '', true), "
                    "set_config('app.demo_token', '', true)"
                )
            )
            assert connection.execute(text("SELECT count(*) FROM public.tenants")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM public.merchants")).scalar_one() == 0

            # Tenant A may create and read only rows whose tenant_id is A.
            connection.execute(text("SELECT set_config('app.tenant_id', 'RLS_CI_A', true)"))
            connection.execute(
                text(
                    "INSERT INTO public.tenants (id, name, created_at) "
                    "VALUES ('RLS_CI_A', 'RLS CI A', now())"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO public.merchants "
                    "(id, tenant_id, name, category, created_at, is_flagship) "
                    "VALUES ('RLS_M_A', 'RLS_CI_A', 'RLS Merchant A', 'test', now(), false)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO public.users "
                    "(id, tenant_id, email, display_name, role, api_token, idp_subject, created_at) "
                    "VALUES ('RLS_U_A', 'RLS_CI_A', 'a@rls.test', 'A', 'ANALYST', "
                    "'rls-token-a', 'rls-sub-a', now())"
                )
            )

            # Tenant B is created only while its own context is active.
            connection.execute(text("SELECT set_config('app.tenant_id', 'RLS_CI_B', true)"))
            connection.execute(
                text(
                    "INSERT INTO public.tenants (id, name, created_at) "
                    "VALUES ('RLS_CI_B', 'RLS CI B', now())"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO public.merchants "
                    "(id, tenant_id, name, category, created_at, is_flagship) "
                    "VALUES ('RLS_M_B', 'RLS_CI_B', 'RLS Merchant B', 'test', now(), false)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO public.users "
                    "(id, tenant_id, email, display_name, role, api_token, idp_subject, created_at) "
                    "VALUES ('RLS_U_B', 'RLS_CI_B', 'b@rls.test', 'B', 'ANALYST', "
                    "'rls-token-b', 'rls-sub-b', now())"
                )
            )

            # Tenant A cannot see B, even when querying the whole table.
            connection.execute(text("SELECT set_config('app.tenant_id', 'RLS_CI_A', true)"))
            tenant_ids = {
                row[0]
                for row in connection.execute(text("SELECT id FROM public.tenants")).all()
            }
            merchant_ids = {
                row[0]
                for row in connection.execute(text("SELECT id FROM public.merchants")).all()
            }
            assert tenant_ids == {"RLS_CI_A"}
            assert merchant_ids == {"RLS_M_A"}

            # A verified OIDC subject can resolve exactly its provisioned user
            # before tenant context exists, then no other user.
            connection.execute(text("SELECT set_config('app.tenant_id', '', true)"))
            connection.execute(text("SELECT set_config('app.oidc_subject', 'rls-sub-b', true)"))
            bootstrap_users = {
                row[0]
                for row in connection.execute(text("SELECT id FROM public.users")).all()
            }
            assert bootstrap_users == {"RLS_U_B"}

            # Demo token bootstrap is equally narrow.
            connection.execute(text("SELECT set_config('app.oidc_subject', '', true)"))
            connection.execute(text("SELECT set_config('app.demo_token', 'rls-token-a', true)"))
            demo_users = {
                row[0]
                for row in connection.execute(text("SELECT id FROM public.users")).all()
            }
            assert demo_users == {"RLS_U_A"}

            # Runtime role must not read or mutate Alembic's migration ledger.
            can_read_migrations = connection.execute(
                text("SELECT has_table_privilege(current_user, 'public.alembic_version', 'SELECT')")
            ).scalar_one()
            assert can_read_migrations is False

            print("RLS runtime verification passed: role, default deny, tenant CRUD visibility, OIDC/demo bootstrap, migration-ledger denial.")
        except Exception:
            transaction.rollback()
            raise
        else:
            transaction.rollback()
    engine.dispose()


if __name__ == "__main__":
    main()
