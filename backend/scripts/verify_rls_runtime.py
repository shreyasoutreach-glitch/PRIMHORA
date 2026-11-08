"""Exercise PostgreSQL RLS as the restricted production runtime role.

Run after Alembic has applied the RLS migration:
    python scripts/verify_rls_runtime.py

All test rows are created in one transaction and rolled back. This is intended
for CI/local Postgres, not the live production database.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings


def main() -> None:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            # Simulate the production login role inheriting the NOLOGIN group.
            # The whole script transaction is rolled back, so this test role
            # never persists in the CI database.
            connection.execute(
                text(
                    "CREATE ROLE primhora_app_ci NOLOGIN INHERIT "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
                )
            )
            connection.execute(text("GRANT primhora_runtime TO primhora_app_ci"))
            connection.execute(text("SET ROLE primhora_app_ci"))
            role = connection.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls, "
                    "pg_has_role(current_user, 'primhora_runtime', 'member') AS runtime_member "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).mappings().one()
            assert role["current_user"] == "primhora_app_ci"
            assert role["rolsuper"] is False
            assert role["rolbypassrls"] is False
            assert role["runtime_member"] is True

            # The role must not own tenant tables and every tenant-keyed
            # public table must have RLS enabled plus the expected policy.
            policy_check = connection.execute(
                text(
                    """
                    WITH tenant_tables AS (
                        SELECT DISTINCT c.oid, c.relname AS table_name,
                               c.relrowsecurity, c.relowner
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        JOIN pg_attribute a ON a.attrelid = c.oid
                        WHERE n.nspname = 'public'
                          AND c.relkind IN ('r', 'p')
                          AND a.attname = 'tenant_id'
                          AND a.attnum > 0
                          AND NOT a.attisdropped
                          AND c.relname <> 'users'
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
                        (SELECT count(*) FROM tenant_tables WHERE relrowsecurity) AS rls_count,
                        (SELECT count(*) FROM tenant_tables
                         WHERE pg_get_userbyid(relowner) = current_user) AS owned_count
                    """
                )
            ).mappings().one()
            assert policy_check["tenant_table_count"] == policy_check["policy_count"]
            assert policy_check["tenant_table_count"] == policy_check["rls_count"]
            assert policy_check["owned_count"] == 0
            privilege_failures = connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_attribute a ON a.attrelid = c.oid
                    WHERE n.nspname = 'public'
                      AND c.relkind IN ('r', 'p')
                      AND a.attname = 'tenant_id'
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                      AND c.relname <> 'users'
                      AND (
                        NOT has_table_privilege('primhora_runtime', c.oid, 'SELECT')
                        OR NOT has_table_privilege('primhora_runtime', c.oid, 'INSERT')
                        OR NOT has_table_privilege('primhora_runtime', c.oid, 'UPDATE')
                        OR NOT has_table_privilege('primhora_runtime', c.oid, 'DELETE')
                      )
                    """
                )
            ).scalar_one()
            assert privilege_failures == 0
            special_policy_count = connection.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE schemaname = 'public' AND policyname IN "
                    "('primhora_tenant_isolation', 'primhora_user_tenant_write', "
                    "'primhora_user_identity_bootstrap')"
                )
            ).scalar_one()
            assert special_policy_count == policy_check["tenant_table_count"] + 3

            connection.execute(
                text(
                    "SELECT set_config('app.tenant_id', '', true), "
                    "set_config('app.oidc_subject', '', true), "
                    "set_config('app.demo_token', '', true)"
                )
            )
            assert connection.execute(text("SELECT count(*) FROM public.tenants")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM public.merchants")).scalar_one() == 0

            no_context_savepoint = connection.begin_nested()
            try:
                connection.execute(
                    text(
                        "INSERT INTO public.tenants (id, name, created_at) "
                        "VALUES ('RLS_NO_CONTEXT', 'Must be rejected', now())"
                    )
                )
            except DBAPIError:
                no_context_savepoint.rollback()
            else:
                no_context_savepoint.rollback()
                raise AssertionError("RLS allowed a tenant insert without tenant context")

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
            assert connection.execute(
                text("UPDATE public.merchants SET name = 'leak' WHERE id = 'RLS_M_B'")
            ).rowcount == 0
            assert connection.execute(
                text("DELETE FROM public.merchants WHERE id = 'RLS_M_B'")
            ).rowcount == 0

            cross_tenant_savepoint = connection.begin_nested()
            try:
                connection.execute(
                    text(
                        "INSERT INTO public.merchants "
                        "(id, tenant_id, name, category, created_at, is_flagship) "
                        "VALUES ('RLS_M_LEAK', 'RLS_CI_B', 'Must be rejected', 'test', now(), false)"
                    )
                )
            except DBAPIError:
                cross_tenant_savepoint.rollback()
            else:
                cross_tenant_savepoint.rollback()
                raise AssertionError("RLS allowed inserting a row for another tenant")

            # A valid same-tenant relationship is accepted.
            connection.execute(
                text(
                    "INSERT INTO public.contacts "
                    "(id, tenant_id, merchant_id, name, type, phone, email, upi_id, created_at) "
                    "VALUES ('RLS_C_A', 'RLS_CI_A', 'RLS_M_A', 'Contact A', "
                    "'vendor', '', 'a-contact@rls.test', '', now())"
                )
            )

            # A tenant-A child row cannot point at a tenant-B merchant, even
            # though the ID-only FK would previously have accepted it.
            composite_fk_savepoint = connection.begin_nested()
            try:
                connection.execute(
                    text(
                        "INSERT INTO public.contacts "
                        "(id, tenant_id, merchant_id, name, type, phone, email, upi_id, created_at) "
                        "VALUES ('RLS_C_LEAK', 'RLS_CI_A', 'RLS_M_B', 'Cross Tenant', "
                        "'vendor', '', 'leak@rls.test', '', now())"
                    )
                )
            except DBAPIError:
                composite_fk_savepoint.rollback()
            else:
                composite_fk_savepoint.rollback()
                raise AssertionError("Composite tenant foreign key allowed a cross-tenant reference")

            composite_fk_count = connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE connamespace = 'public'::regnamespace "
                    "AND contype = 'f' AND conname LIKE 'fk_%_tenant_%'"
                )
            ).scalar_one()
            assert composite_fk_count == 21

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

            # Exercise the real application Session hook, not just raw
            # set_config calls. This verifies the after_begin listener applies
            # context and reapplies it after a commit/new transaction.
            from app.core.tenancy import TenantScopedSession
            from app.models.entities import Merchant

            session = TenantScopedSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
            )
            session.set_tenant("RLS_CI_A")
            orm_a = session.execute(select(Merchant)).scalars().all()
            assert {merchant.id for merchant in orm_a} == {"RLS_M_A"}
            assert session.get(Merchant, "RLS_M_B") is None
            session.commit()

            # The same session starts another transaction; its context must be
            # re-applied by after_begin rather than relying on pooled state.
            orm_a_again = session.execute(select(Merchant)).scalars().all()
            assert {merchant.id for merchant in orm_a_again} == {"RLS_M_A"}
            session.set_tenant("RLS_CI_B")
            orm_b = session.execute(select(Merchant)).scalars().all()
            assert {merchant.id for merchant in orm_b} == {"RLS_M_B"}
            session.close()

            # Runtime role must not read or mutate Alembic's migration ledger.
            can_read_migrations = connection.execute(
                text("SELECT has_table_privilege(current_user, 'public.alembic_version', 'SELECT')")
            ).scalar_one()
            assert can_read_migrations is False

            print("RLS verification passed: restricted inherited role, default deny, tenant CRUD isolation, composite-FK enforcement, OIDC/demo bootstrap, least-privilege grants, migration-ledger denial.")
        except Exception:
            transaction.rollback()
            raise
        else:
            transaction.rollback()
    engine.dispose()


if __name__ == "__main__":
    main()
