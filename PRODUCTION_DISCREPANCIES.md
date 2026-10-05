# Production Discrepancy Register

Reviewed against the current PRIMHORA repository and deployment topology on 3 October 2026.

This is an engineering gap register, not a claim that every item blocks the capstone.

## Fixed in the current hardening passes

| Area | Discrepancy | Action |
|---|---|---|
| Demo bootstrap | /api/demo/session was behind the authenticated admin dependency, creating a bootstrap deadlock. | Demo session issuance now uses the database dependency directly and remains gated by DEMO_MODE; destructive demo reset/injection remain administrator-only. |
| API routing | Vercel pointed at a stale Render backend hostname. | Canonical rewrite now targets the live Render API service. |
| Demo availability | Demo identity could disappear when the seeded database was reset. | Stable demo bootstrap configuration and backend-seeded demo identity are used. |
| Frontend source count | Dashboard could show a connected source merely because a workspace existed. | Metric now reflects accepted CSV imports in the current browser session. |
| Merchant identity | CSV import could derive the merchant from the workspace name. | Merchant/business is now explicit at import time. |
| Production authentication gate | Startup checked issuer/audience but could still be incomplete without a usable JWKS endpoint. | Startup now requires issuer, audience and resolved JWKS configuration before DEMO_MODE=false can boot. |
| JWT test contract | Tests still modeled pre-hardening email-based lookup. | Fixture now validates immutable idp_subject provisioning. |
| Attestation eligibility | Attestation endpoint hard-coded investigation signals instead of using the incident's actual score components. | Candidate-question generation is shared with the read endpoint and driven by the stored incident signals. |
| Security headers | API responses lacked application-level browser protections. | Added MIME, clickjacking, referrer, permissions, CSP, HSTS and API no-store headers. |
| Health disclosure | Public health/root response exposed unnecessary deployment configuration. | Health response is limited to non-sensitive status/service fields. |
| Metrics exposure | Metrics/evaluation endpoints were authenticated inconsistently. | VIEW permission is required. |
| Evidence integrity | Evidence upload did not verify merchant/incident ownership. | Upload validates tenant-owned merchant and incident relationships. |
| Vision errors | Extraction errors could expose raw provider exception text. | Client receives a generic failure while the artifact remains unverified. |
| Deployment IaC | Render blueprint contained stale/destructive startup behavior and stale frontend origins. | Blueprint was aligned with the current deployment model. |

## Newly closed in the current production-hardening pass

| Area | Discrepancy | Action |
|---|---|---|
| Supabase Data API exposure | `anon`/`authenticated` retained default table privileges despite RLS being enabled. | Revoked table, sequence and function privileges for both roles and codified the change as a migration. |
| Database readiness | `/health` returned 200 without checking PostgreSQL connectivity. | `/health` now executes `SELECT 1` and returns 503 when the production database is unavailable. |

## Still not normal for a production MVP

| Area | Current state | Required before external customer data |
|---|---|---|
| Authentication | Demo bearer sessions remain enabled on the live environment. | Activate a real OIDC provider and set DEMO_MODE=false. |
| User provisioning | Production users are resolved by immutable IdP subject and must already exist. | Add durable organization membership, invitation and provisioning lifecycle. |
| Workspace membership | A user currently carries one tenant_id; self-service provisioning is demo-only. | Introduce production organization/membership modeling. |
| Evidence storage | New evidence bytes are persisted in the primary database; filesystem storage remains a compatibility/access path. | Formalize database backup/restore, retention and storage-sizing policy; object storage remains preferable at larger evidence volumes. |
| Provider coverage | Generic payout CSV is the verified ingestion path; live provider adapters are limited. | Add and test the first customer-required provider adapter and reconciliation flow. |
| Webhooks | Razorpay webhook configuration is environment-wide and tied to one merchant. | Make credentials and webhook routing tenant-aware and operationally managed. |
| Abuse controls | No distributed request rate limiting or abuse policy is implemented. | Add edge/application rate limiting for auth, uploads and expensive endpoints. |
| Observability | Basic deployment logs exist, but product-level alerting, request correlation, SLOs and a tested incident runbook are not established. | Add structured logs, correlation IDs, error tracking, alerts and restore drills. |
| Database migrations | Alembic is the deployment migration path; demo seed code can still create tables for standalone synthetic setup. | Keep external-customer production schema lifecycle solely under migrations and keep seed-only table creation out of production startup. |
| Deployment verification | CI verifies frontend build, backend tests and Docker health; live browser verification remains manual. | Run a deployed smoke suite through demo and the first investigation workflow. |
| Frontend topology | Canonical PRIMHORA frontend is Vercel; legacy Render frontend resources may still exist in historical topology. | Retire duplicate frontend resources after verification. |
| Recovery | Recovery commands are simulated and read-only by design. | Preserve this boundary unless a future governed execution integration is deliberately added. |

## Production gate

PRIMHORA should not be described as ready for real customer financial data until the authentication, durable evidence storage, membership provisioning, provider integration, observability and deployed-browser verification gates above are closed.

The purpose of this register is to prevent a green CI badge from becoming a substitute for production engineering.
