# ADR: Safe PostgreSQL tenant-RLS rollout

**Status:** Implementation prepared on `security/postgres-rls-runtime-role`; not merged or deployed. No production SQL or credentials changed.
**Scope:** PRIMHORA's Supabase PostgreSQL database and Render API runtime.

## Executive decision

Do not add tenant policies to the live database until the application runtime is moved off a privileged database role and the identity bootstrap path is redesigned. The current database has RLS enabled on 27 public tables, but zero policies. The existing application depends on global user lookup and system-scoped sessions. A policy-only migration would either break authentication/operations or tempt us to add a broad bypass.

The implementation branch now contains a staged first cut: a NOLOGIN `primhora_runtime` group role, tenant policies, transaction-local context wiring, and a PostgreSQL role-level verification script. A separate LOGIN role and production credential switch remain activation steps. The target is:

1. A dedicated app_runtime login role that is not a table owner, is not a member of a privileged role, and has neither SUPERUSER nor BYPASSRLS.
2. A separate migration credential/role with schema-owner privileges. Runtime startup must not run Alembic using the application credential.
3. Transaction-local tenant context set only after OIDC token verification and user-to-tenant resolution.
4. Default-deny RLS policies on every tenant-owned table, with USING and WITH CHECK.
5. A narrowly scoped identity bootstrap policy for users, not a global user-table read.
6. Regression tests against real PostgreSQL using the same non-bypass role used by the deployed application.

RLS is defense in depth against missing tenant predicates. A custom PostgreSQL GUC such as app.tenant_id is not a cryptographic capability: code executing arbitrary SQL as the runtime role could set it. This design does not claim to contain SQL injection or a fully compromised application credential.

## Verified current-state findings

The 2026-11-07 Supabase inspection found:

- 27 public tables.
- RLS enabled on all 27.
- Zero RLS policies.
- Zero direct table grants to anon, authenticated, or PUBLIC.
- postgres and service_role have BYPASSRLS; anon, authenticated, and authenticator do not.
- No table had FORCE ROW LEVEL SECURITY enabled.
- The Render service uses Supabase PostgreSQL Session Pooler. The actual Render database username was not exposed by the service-inspection connector, so the live connection role still needs confirmation.

The checked-in migration d6f4a2b8c1e0_production_rls_and_fk_indexes.py only enables RLS and creates indexes. It creates no policies and does not FORCE RLS.

The checked-in Render Blueprint currently starts the service with:

~~~sh
cd backend && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
~~~

That means simply replacing DATABASE_URL with a restricted runtime role would break startup migrations unless migration execution is separated first.

## Application paths that must be accounted for

- get_current_user verifies the OIDC JWT, then globally looks up users.idp_subject. A tenant policy cannot simply require tenant_id = current_setting(...) before this lookup because the tenant is not known yet.
- get_tenant_db assigns the authenticated user's tenant to the session.
- get_system_db intentionally clears tenant scope and is used by workspace provisioning and demo administration paths.
- Workspace creation, demo injection, and demo reset are demo-only or explicitly disabled in production by route logic. Confirm every call site and dependency order before production RLS is enabled.
- The runtime currently shares one DATABASE_URL with Alembic startup. This must be split into runtime and migration credentials.

## Target database roles

### app_runtime

- LOGIN role for the Render API only.
- NO SUPERUSER, NO BYPASSRLS, NO CREATEDB, NO CREATEROLE.
- Must not own tenant tables and must not inherit membership in a bypass/owner role.
- Grant only required schema usage and table DML. Do not grant DDL or access to alembic_version.
- Use the Session Pooler-compatible username/connection string format and verify the effective role with current_user, session_user, rolsuper, rolbypassrls, and role-membership inspection.

### schema_migrator

- Separate credential used only by the release/migration process.
- Owns or has explicit DDL rights on the application schema.
- Never supplied to the running API process.
- Migrations must run as a controlled release step, not as a side effect of each web instance starting.

Do not store either credential in Git. Set secrets directly in the deployment provider. Never paste a password into chat or a PR.

## Tenant context contract

After OIDC signature, issuer, audience, expiry, and subject validation:

1. Set transaction-local app.oidc_subject to the verified immutable subject.
2. Query exactly the matching provisioned user row through the bootstrap policy on users.
3. Clear app.oidc_subject for the rest of the transaction once the user has been resolved.
4. Set transaction-local app.tenant_id to the resolved user's tenant ID before any tenant-owned data query.
5. Re-apply the tenant setting on every new transaction. Use transaction-local settings (set_config(..., true)), never session-wide settings, so pooled connections cannot leak context between requests.
6. For requests without a resolved tenant, tenant-owned tables remain default-deny.

The SQLAlchemy implementation must handle the fact that FastAPI dependencies may share one Session and one transaction. In particular, set_tenant must update the active transaction, and a Session after_begin hook (or equivalent tested mechanism) must reapply tenant context to later transactions. Do not rely on setting a session-level GUC and hoping the pool resets it.

## Policy matrix

| Table class | Policy |
|---|---|
| Tenant-owned tables (25 tables with tenant_id) | SELECT/UPDATE/DELETE USING tenant_id = current_setting('app.tenant_id', true); INSERT/UPDATE WITH CHECK same predicate |
| tenants | Tenant can read only the row whose id equals app.tenant_id; inserts/provisioning handled by a separate narrowly scoped operation |
| users | Normal access limited to tenant_id = app.tenant_id; bootstrap lookup may additionally select only the row whose idp_subject equals verified app.oidc_subject |
| alembic_version | No runtime grant; migration role only |

Enable RLS on tenant-owned tables after role and policy tests are ready. `primhora_app` must be neither table owner nor BYPASSRLS. FORCE RLS is intentionally omitted so local owner-based development seeding continues to work; this does not weaken RLS for the separate non-owner production runtime role.

Use explicit policies per command (SELECT, INSERT, UPDATE, DELETE) or a carefully reviewed combined policy. Verify every policy's USING and WITH CHECK semantics. Do not use a permissive true policy for system access.

## System operations

Production tenant traffic should use tenant-scoped DB sessions only. The current system-scoped routes are primarily demo/provisioning functionality, but this must be confirmed by enumerating all get_system_db call sites and testing the production configuration.

If any genuine cross-tenant production operation remains, implement it as a narrowly scoped database function with:
- fixed, minimal search_path;
- explicit argument validation;
- explicit authorization checks;
- a limited result/command surface;
- no generic "set system admin" GUC or unrestricted bypass role exposed to ordinary request code.

Do not grant the runtime role a general-purpose cross-tenant bypass just to keep legacy admin endpoints working.

## Referential integrity gap

Many foreign keys currently reference only the child ID, not the pair (tenant_id, id). PostgreSQL foreign-key checks are not a substitute for tenant ownership checks and can permit a row in one tenant to reference a known row in another tenant. After RLS is in place, add a separate integrity migration: unique composite keys on (tenant_id, id) and matching composite foreign keys for tenant-owned relationships, after validating existing data. Do not combine this with the first RLS cutover.

## Rollout sequence and gates

### Phase 0: inventory and credential confirmation
- Confirm the live Render DATABASE_URL username/role without revealing the password.
- Enumerate all get_system_db, raw SQL, Core SQL, direct engine, and background-task access.
- Identify all production routes that can create or read across tenants.
- Confirm actual tenant ownership and check for orphaned/cross-tenant foreign-key relationships.

### Phase 1: split runtime and migration credentials
- Create the non-bypass runtime role and separate migration credential.
- Update the release process to run Alembic with the migration credential.
- Deploy the split with existing policies still unchanged; verify app health and migration behavior.
- Verify current_user at runtime is the restricted role.

### Phase 2: application transaction context
- Implement and test transaction-local OIDC-subject bootstrap and tenant context.
- Ensure context is reapplied after commit/rollback and across pooled connection reuse.
- Remove or disable production system-scope routes that are not required.
- Run the complete suite against PostgreSQL, not only SQLite.

### Phase 3: policies on a non-production database branch
- Apply policies and FORCE RLS in a Supabase development branch.
- Run cross-tenant SELECT, INSERT, UPDATE, DELETE, primary-key lookup, joined query, background task, webhook, and evidence tests using the exact app_runtime role.
- Verify no tenant context means no tenant rows.
- Verify user bootstrap can see only its matching subject.
- Verify tenant A cannot reference tenant B rows through writes.

### Phase 4: production cutover
- Take and verify a restorable backup first.
- Schedule a controlled maintenance window.
- Apply policies with migration credentials.
- Switch Render to the restricted runtime URL.
- Verify role attributes, policies, request health, authentication, tenant isolation, and rollback readiness.
- Keep the previous credential disabled/rotated after the cutover is proven.

## Required acceptance tests

1. No tenant context: every tenant-owned table returns zero rows and rejects writes.
2. Tenant A can read/write its own rows.
3. Tenant A cannot read/update/delete Tenant B rows by list query, primary key, ORM select, join, or raw SQL.
4. Tenant A cannot insert a row with Tenant B's tenant ID.
5. Tenant A cannot create a cross-tenant foreign-key reference.
6. Verified OIDC subject can resolve only its own provisioned user.
7. Unknown subject returns no user and cannot access tenant data.
8. Context does not survive commit, rollback, connection return, or reuse by another request.
9. Runtime role is not owner, superuser, or BYPASSRLS and has no privileged role membership.
10. Migration role can migrate; runtime role cannot perform DDL or alter policies.
11. Production demo/reset/provisioning routes remain correctly disabled or are implemented through a narrow authorized mechanism.

## Composite foreign-key integrity

The implementation branch adds migration `f3a8d1c6e9b2_tenant_composite_foreign_keys.py`. It replaces 21 ID-only foreign keys between tenant-owned tables with composite `(tenant_id, referenced_id)` foreign keys, backed by `(tenant_id, id)` unique constraints on parent tables. A read-only live audit on 2026-11-08 found zero cross-tenant mismatches across all 21 relationships. The migration repeats this preflight and aborts atomically if any mismatch exists. Docker CI verifies that a Tenant A row cannot reference a Tenant B merchant. The migration is not applied to production.

## Rollback

Rollback must restore the previous application credential and application release only after confirming the prior credential remains valid and has been rotated/controlled. Disabling RLS as a quick rollback is not acceptable. Keep migration scripts reversible where possible, but never drop role/policy objects automatically without reviewing dependencies.

## Explicit non-goals

- No live database changes in this ADR or its implementation branch.
- No credentials or secrets in source control.
- No generic privileged system GUC.
- No claim that RLS alone prevents SQL injection.
- No production cutover until PostgreSQL role-level tests pass.
