# PostgreSQL RLS activation runbook

**Status:** Prepared with the security branch. Do not perform the production cutover until the branch is merged, CI is green, a restorable backup is verified, and OIDC production configuration is confirmed.

## What the branch migration does

```text
e7f1c9a4b2d6_tenant_rls_runtime_role.py
```

- Creates `primhora_runtime` as a NOLOGIN, NOBYPASSRLS group role.
- Grants schema usage, tenant-table DML, and sequence usage.
- Revokes access to `public.alembic_version`.
- Adds default-deny policies to every public base table with `tenant_id`.
- Adds a tenant-ID policy to `tenants`.
- Adds tenant-scoped writes plus exact OIDC-subject/demo-token SELECT bootstrap policies to `users`.
- Does not create a login role, set a password, or change Render's current runtime credential.

The existing production credential remains unchanged until the final cutover. If it is still `postgres`, it bypasses RLS. The migration alone does not mean production isolation is active.

## Pre-cutover checks

1. Merge the hardening stack in order: PR #11, then PR #12, then PR #13, then this RLS implementation PR.
2. Confirm the latest GitHub Actions run passes backend tests, frontend build, Docker startup, and `verify_rls_runtime.py`.
3. In Supabase, confirm a recent backup exists and perform a restore test in a separate project/branch. Do not assume backups are restorable merely because they are listed.
4. Confirm the production OIDC provider values are configured in Render: issuer, audience, JWKS URL. The app intentionally refuses startup in non-demo mode if these are missing.
5. Confirm production `DEMO_MODE=false`, `DEMO_BOOTSTRAP_ON_START=false`, and `DEMO_ALLOW_GLOBAL_RESET=false`. Do not expose the demo login endpoint in a customer-facing production deployment.
6. If Razorpay webhooks are enabled, set `RAZORPAY_TENANT_ID` to the same tenant that owns the configured merchant. The webhook now requires this binding.
7. Configure Render's health check path as `/health` and verify it is actually saved in the live service settings.

## Configure the migration credential first

In Render, add `MIGRATION_DATABASE_URL` as a secret. It should use the existing database-owner/migration credential and the same Supabase database. For the current persistent Render service, use the Supabase Session Pooler connection string (port 5432) unless the service's connection topology has intentionally changed.

Keep the existing `DATABASE_URL` unchanged during this step. Alembic now prefers `MIGRATION_DATABASE_URL`; the API process continues to use `DATABASE_URL`.

Never put the password in Git, issue comments, or chat.

## Create the login role after the migration is deployed

After Alembic has applied the branch migration, run this in the Supabase SQL Editor as the database owner. Generate a unique strong password in a password manager and substitute it locally. Do not paste it into chat.

```sql
CREATE ROLE primhora_app
  LOGIN
  INHERIT
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOREPLICATION
  NOBYPASSRLS
  PASSWORD '<GENERATE_A_UNIQUE_PASSWORD>';

GRANT primhora_runtime TO primhora_app;
```

Verify the role before using it:

```sql
SELECT
  r.rolname,
  r.rolcanlogin,
  r.rolsuper,
  r.rolbypassrls,
  r.rolcreatedb,
  r.rolcreaterole,
  pg_has_role(r.rolname, 'primhora_runtime', 'member') AS is_runtime_member
FROM pg_roles r
WHERE r.rolname = 'primhora_app';
```

Expected: LOGIN true; SUPERUSER, BYPASSRLS, CREATEDB, CREATEROLE false; runtime membership true.

Also verify that `primhora_app` does not own any application tables and is not a member of `postgres` or `service_role`.

## Construct the Render runtime URL

Use the Supabase Session Pooler URL shown in the project's Connect dialog. For Supavisor shared pooler URLs, the username includes the project reference. Replace the role part of the username with `primhora_app` while retaining the project-reference suffix, host, port, database, SSL settings, and URL encoding.

Example shape only:

```text
postgresql+psycopg2://primhora_app.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

Do not copy this example host or region blindly. Use the exact host and port displayed by the Supabase dashboard. Keep session mode (5432) for this persistent Render service. Store the finished value only in Render's secret environment variable.

Set Render:
- `DATABASE_URL` = the new `primhora_app` runtime connection.
- `MIGRATION_DATABASE_URL` = the owner/migration connection.
- `DEMO_MODE` = `false` after verifying OIDC settings.
- `DEMO_BOOTSTRAP_ON_START` = `false`.
- `DEMO_ALLOW_GLOBAL_RESET` = `false`.

Deploy during a monitored window. Do not remove or rotate the migration credential during the first successful release.

## Post-deploy verification

1. Render deploy completes and `/health` returns HTTP 200.
2. OIDC login succeeds for a provisioned user.
3. A tenant user can read their own workspace and records.
4. A second tenant's IDs return no rows/404 and cannot be updated or deleted.
5. The Docker/PostgreSQL RLS verification script passes against the exact policy migration.
6. Inspect database activity/connection role metadata to confirm the live API connection is `primhora_app`, not `postgres`.
7. Run Supabase security advisors and confirm no exposed table is missing its intended RLS policy.
8. Verify webhook delivery only writes to the configured tenant, if enabled.
9. Confirm global demo reset is rejected under `primhora_app`.

## Rollback

If the app fails after switching `DATABASE_URL`, restore the previous runtime URL in Render while keeping `MIGRATION_DATABASE_URL` intact. The previous owner credential bypasses RLS, so this restores the prior behavior while the issue is investigated. Do not drop policies or disable RLS as an emergency shortcut. Once the restricted runtime deployment is stable, rotate/disable the previous runtime credential according to the database access policy.

## Known remaining security work

- [Branch migration] `f3a8d1c6e9b2_tenant_composite_foreign_keys.py` replaces all 21 ID-only tenant-to-tenant references with composite tenant-aware foreign keys. A read-only audit of the live database on 2026-11-08 found zero cross-tenant mismatches; the migration repeats the preflight and aborts if any appear. The migration is not yet applied to production.
- Production backup/restore verification: not yet confirmed.
- Render's live environment variable values and live health-check setting: not exposed by the inspection connector; verify in the dashboard.
- The custom `app.tenant_id` GUC is transaction-local and validated by application flow, but it is not a cryptographic capability. RLS is defense in depth against missing predicates, not a substitute for SQL-injection prevention or a boundary against a fully compromised app credential.