"""Install a non-bypass runtime role and tenant RLS policies.

Revision ID: e7f1c9a4b2d6
Revises: d6f4a2b8c1e0

This migration is additive. It creates a NOLOGIN group role; it does not
change the credentials used by the running Render service. A login role must
later be created and granted membership, then DATABASE_URL switched after
the separate migration credential is configured.
"""
from alembic import op

revision = "e7f1c9a4b2d6"
down_revision = "d6f4a2b8c1e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles
                WHERE rolname = 'primhora_runtime'
            ) THEN
                CREATE ROLE primhora_runtime
                    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOINHERIT NOREPLICATION NOBYPASSRLS;
            ELSE
                IF EXISTS (
                    SELECT 1 FROM pg_catalog.pg_roles
                    WHERE rolname = 'primhora_runtime'
                      AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole)
                ) THEN
                    RAISE EXCEPTION
                        'Existing primhora_runtime role has unsafe elevated attributes';
                END IF;
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO primhora_runtime")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON ALL TABLES IN SCHEMA public TO primhora_runtime"
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON TABLE public.alembic_version "
        "FROM primhora_runtime"
    )
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO primhora_runtime"
    )

    # Every tenant-owned table, including the four risk-engine tables that do
    # not inherit the application's TenantScoped mixin, receives the same
    # fail-closed tenant predicate.
    op.execute(
        """
        DO $$
        DECLARE
            item record;
        BEGIN
            FOR item IN
                SELECT DISTINCT c.table_name
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema
                 AND t.table_name = c.table_name
                WHERE c.table_schema = 'public'
                  AND c.column_name = 'tenant_id'
                  AND t.table_type = 'BASE TABLE'
                  AND c.table_name NOT IN ('users', 'alembic_version')
                ORDER BY c.table_name
            LOOP
                EXECUTE format(
                    'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                    item.table_name
                );
                EXECUTE format(
                    'ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',
                    item.table_name
                );
                EXECUTE format(
                    'CREATE POLICY primhora_tenant_isolation ON public.%I '
                    'FOR ALL TO primhora_runtime '
                    'USING (tenant_id::text = nullif(current_setting(''app.tenant_id'', true), '''')) '
                    'WITH CHECK (tenant_id::text = nullif(current_setting(''app.tenant_id'', true), ''''))',
                    item.table_name
                );
            END LOOP;
        END
        $$;
        """
    )

    # Tenant rows are visible and mutable only when their own ID is the
    # transaction-local tenant context.
    op.execute("ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY primhora_tenant_isolation ON public.tenants
        FOR ALL TO primhora_runtime
        USING (id::text = nullif(current_setting('app.tenant_id', true), ''))
        WITH CHECK (id::text = nullif(current_setting('app.tenant_id', true), ''))
        """
    )

    # User lookup before tenant scope is established is narrowly permitted
    # only by the verified OIDC subject or exact demo bearer token. Once the
    # user is resolved, the app clears the bootstrap setting and applies the
    # user's tenant context. Writes remain tenant-scoped.
    op.execute("ALTER TABLE public.users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.users FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY primhora_user_tenant_write ON public.users
        FOR ALL TO primhora_runtime
        USING (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))
        """
    )
    op.execute(
        """
        CREATE POLICY primhora_user_identity_bootstrap ON public.users
        FOR SELECT TO primhora_runtime
        USING (
            idp_subject = nullif(current_setting('app.oidc_subject', true), '')
            OR api_token = nullif(current_setting('app.demo_token', true), '')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS primhora_user_identity_bootstrap ON public.users"
    )
    op.execute("DROP POLICY IF EXISTS primhora_user_tenant_write ON public.users")
    op.execute(
        "DROP POLICY IF EXISTS primhora_tenant_isolation ON public.tenants"
    )
    op.execute(
        """
        DO $$
        DECLARE
            item record;
        BEGIN
            FOR item IN
                SELECT DISTINCT table_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND column_name = 'tenant_id'
                  AND table_name NOT IN ('users', 'alembic_version')
            LOOP
                EXECUTE format(
                    'DROP POLICY IF EXISTS primhora_tenant_isolation ON public.%I',
                    item.table_name
                );
            END LOOP;
        END
        $$;
        """
    )
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM primhora_runtime")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM primhora_runtime")
    op.execute("REVOKE USAGE ON SCHEMA public FROM primhora_runtime")
    op.execute("DROP ROLE IF EXISTS primhora_runtime")
