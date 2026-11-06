# Primhora production authentication

Primhora uses browser OIDC Authorization Code with PKCE for the protected `/app/*` workspace. The browser never receives a client secret. The backend validates the signed access token against issuer, audience, expiration, issuer and immutable `sub`.

## Auth0 application

Create an Auth0 **Single Page Application**.

Configure these exact application URLs:

~~~text
Allowed Callback URL: https://YOUR-PRIMHORA-DOMAIN/app
Allowed Logout URL: https://YOUR-PRIMHORA-DOMAIN/
Allowed Web Origin: https://YOUR-PRIMHORA-DOMAIN
~~~

Auth0 requires exact callback URL matching. Do not use wildcard production callbacks.

Create/configure an Auth0 API and use its API Identifier as `VITE_AUTH0_AUDIENCE` and `AUTH_PROVIDER_AUDIENCE`.

Use Authorization Code + PKCE. Do not put a client secret in Vercel.

## Vercel environment

~~~text
VITE_API_BASE_URL=
VITE_AUTH_REQUIRED=true
VITE_AUTH0_DOMAIN=YOUR_AUTH0_DOMAIN
VITE_AUTH0_CLIENT_ID=YOUR_SPA_CLIENT_ID
VITE_AUTH0_AUDIENCE=YOUR_API_IDENTIFIER
~~~

`VITE_API_BASE_URL` stays empty because the application uses the relative `/api` path and Vercel rewrites it to Render.

## Render environment

~~~text
DEMO_MODE=false
AUTH_PROVIDER_DOMAIN=YOUR_AUTH0_DOMAIN
AUTH_PROVIDER_ISSUER=https://YOUR_AUTH0_DOMAIN/
AUTH_PROVIDER_AUDIENCE=YOUR_API_IDENTIFIER
AUTH_PROVIDER_JWKS_URL=https://YOUR_AUTH0_DOMAIN/.well-known/jwks.json
CORS_ORIGINS=
~~~

Keep provider secrets and Razorpay credentials on Render, never in Vercel `VITE_*` variables.

## Provisioning

Authentication and application authorization are separate on purpose.

After authentication, the backend requires the immutable OIDC `sub` to exist in `users.idp_subject`. Provision the first founder/admin identity from the Render shell:

~~~bash
cd backend
python scripts/provision_oidc_user.py --subject 'AUTH0_SUBJECT' --email 'you@example.com' --name 'Your Name' --role ADMINISTRATOR --tenant-name 'Your Company'
~~~

Provision additional users with `ANALYST`, `FINANCE_OPERATOR`, `INVESTIGATOR`, or `APPROVER`.

Do not use email as the identity key. Email is mutable; `sub` is the identity binding used by the API.

## Demo mode

Demo mode remains available for sales walkthroughs, but it must be explicit:

~~~text
DEMO_MODE=true
VITE_AUTH_REQUIRED=false
~~~

Do not use demo mode for real customer data. The shared public demo credential is intentionally non-customer isolation. CSV ingestion and evidence uploads are blocked by default while demo mode is active, and provider webhooks are disabled. Do not set `DEMO_ALLOW_EXTERNAL_INGESTION=true` on a shared deployment. Configure and test OIDC, set `VITE_AUTH_REQUIRED=true` and `DEMO_MODE=false`, then provision each user by immutable provider `sub` before receiving any customer financial records.

## Security checks

- PKCE S256 is used for every browser login.
- OAuth `state` is generated per login and verified on callback.
- Access tokens are kept in memory only for the active page session.
- The API validates JWT signature, issuer, audience, expiration, issued-at, subject and JWKS.
- Tenant context is derived from the authenticated user.
- System-wide database access requires the Administrator role.
- Workspace reads are tenant-scoped.
- API responses are marked `no-store`.
- High-risk recovery operations retain server-side RBAC/state-machine enforcement.

For smoother browser refreshes later, add Auth0 refresh-token rotation or silent authentication through a custom Auth0 domain rather than persisting access tokens in localStorage.