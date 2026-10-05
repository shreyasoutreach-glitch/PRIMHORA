# PRIMHORA

**Financial Incident Intelligence**

PRIMHORA is a read-only financial incident investigation and evidence-reconstruction platform.

It is designed for the moment after something has gone wrong: fragmented payment records, bank exports, invoices, communications, screenshots and human context need to become a traceable answer.

> **What happened? What can we prove? What is exposed? What still requires a human decision?**

PRIMHORA is intentionally not a payment executor, autonomous fraud judge, or banking control plane.

## Why PRIMHORA exists

Traditional payment-fraud products often focus on prevention, vendor validation, payment controls or anomaly detection before money moves.

PRIMHORA targets a different workflow:

**incident → evidence → reconstruction → correlation → human context → exposure → governed recovery packet**

The core rule is:

> **AI can interpret. Deterministic records establish financial truth. Humans resolve what machines cannot know.**

An extracted amount, beneficiary or instruction is never promoted to authoritative financial truth merely because a model produced it.

## Core workflow

1. Ingest source-backed financial data.
2. Normalize it into canonical financial events.
3. Detect anomalous incident signals with deterministic rules.
4. Reconstruct the incident timeline.
5. Correlate entities, communications and source records.
6. Collect evidence with hashes, provenance and verification states.
7. Ask a human the smallest high-value unresolved question.
8. Calculate exposure across confirmed, pending, attempted and related amounts.
9. Prepare a recovery packet with source references and audit history.
10. Verify convergence by deterministic re-computation.

PRIMHORA is read-only. It does not initiate, freeze, reverse, or claim to recover money.

## What differentiates it

PRIMHORA should not be positioned as generic "AI fraud detection." That category already includes payment monitoring, anomaly detection, vendor-bank verification and preventive controls.

The narrower product wedge is **financial incident intelligence and evidence reconstruction after a suspected incident**.

The useful output is therefore not only a score. It is a defensible case containing:

- source-backed financial facts;
- a deterministic incident timeline;
- entity relationships and bounded blast radius;
- evidence artifacts and hashes;
- candidate claims with VERIFIED / CONFLICTING / UNVERIFIED states;
- human attestations stored separately from financial facts;
- deterministic exposure;
- an auditable recovery/investigation packet.

The commercial thesis remains a hypothesis. Real investigators and finance teams still need to validate the workflow and willingness to pay.

## Architecture

### Frontend

- React 18
- TypeScript
- Vite
- React Router
- Tailwind CSS
- Lucide
- Framer Motion

The frontend uses `frontend/src/lib/api.ts` as the API boundary.

### Backend

- FastAPI
- SQLAlchemy
- Pydantic
- Alembic
- PostgreSQL locally and in production
- PyJWT + JWKS validation for production OIDC
- pypdf and ReportLab for evidence/packet handling

Key service boundaries:

- `financial/` → deterministic baselines and anomaly primitives
- `incident/` → detection, scoring and state transitions
- `entity/` → identifier-first entity resolution
- `temporal/` → interval-aware event ordering
- `evidence/` → hashing, MIME validation, extraction and claim handling
- `graph/` → source-backed relationships and bounded blast radius
- `exposure/` → deterministic financial exposure
- `human/` → prioritized human questions
- `recovery/` → proposal/review/approval/packet/convergence workflow
- `audit/` → application audit events
- `evaluation/` → reproducible fixture evaluation
- `seed/` → deterministic synthetic data generation

See [ARCHITECTURE.md](ARCHITECTURE.md) for the system diagram and data model.

## Financial truth boundary

### Authoritative financial records

Payouts and normalized financial events come from source records or explicitly accepted imports.

### Candidate evidence

Text, images and scanned PDFs can produce claims such as an amount, beneficiary or instruction. These remain untrusted until deterministic cross-reference rules verify them against canonical financial events.

### Human context

Attestations are stored as their own records. They can change case interpretation or state, but they do not rewrite historical financial records.

This separation is an architectural constraint, not just UI copy.

## Incident Evidence Score

PRIMHORA currently combines six deterministic signals:

| Signal | Weight |
|---|---:|
| New beneficiary | 25 |
| Amount anomaly | 20 |
| Velocity anomaly | 20 |
| Historical novelty | 15 |
| Dormant entity | 10 |
| Communication correlation | 10 |

The result is an **Incident Evidence Score**, not a fraud probability.

The implementation uses deterministic rules and robust statistics such as median/MAD and rolling-window behavior rather than an LLM-generated financial score.

## Entity resolution

Matching is identifier-first. Strong identifiers such as transaction IDs, fund-account IDs and UPI IDs can support automatic linkage. Weaker signals such as names, addresses and temporal similarity remain review signals.

Name similarity alone cannot produce an `AUTO_LINK` decision.

## Evidence handling

Uploaded evidence is:

- size limited;
- MIME validated;
- SHA-256 hashed;
- bound to tenant, merchant and incident ownership;
- stored as bytes for new uploads in the primary database;
- optionally interpreted through deterministic PDF/text extraction or Gemini multimodal extraction;
- represented as candidate claims before verification.

The local filesystem is still used as an access/fallback path. Production backup, retention, restore procedures and storage sizing remain operational gates.

## Recovery boundary

The governed recovery workflow is:

`PROPOSED → REVIEWED → APPROVED → PACKET_READY → VERIFIED`

Proposal, review and approval have distinct RBAC checks. Approval cannot be performed by the same user who proposed the command.

The current `/execute` endpoint deliberately returns HTTP 409 and performs no external financial action.

PRIMHORA therefore **prepares and verifies a recovery packet; it does not execute an external financial action**.

## Multi-tenancy and authentication

### Demo mode

Demo mode uses synthetic bearer credentials and a seeded synthetic tenant. The demo-session endpoint is the unauthenticated bootstrap surface, and it is available only when `DEMO_MODE=true`. Destructive demo reset/injection operations remain administrator-only.

### Production mode

Production uses browser OIDC Authorization Code + PKCE and backend JWT verification.

The backend validates:

- signature;
- issuer;
- audience;
- expiration;
- issued-at;
- immutable `sub`;
- JWKS.

Application access is then resolved from the provisioned `users.idp_subject` record.

If production authentication is incomplete, the backend fails closed.

See [docs/PRODUCTION_AUTH.md](docs/PRODUCTION_AUTH.md).

## Deployment topology

- **UI:** Vercel
- **API:** Render
- **Production UI:** https://primhora.vercel.app
- **API:** Render web service (legacy Render subdomain retained temporarily; application identity is PRIMHORA)

The canonical Vercel deployment rewrites `/api/*` to the Render API.

Local Docker Compose provides a PostgreSQL + FastAPI + frontend stack.

## Local development

### Docker Compose

From the repository root:

```bash
docker compose up -d --build
```

Open `http://localhost:8080` and check `http://localhost:8000/health` for backend health.

Stop the stack with:

```bash
docker compose down
```

Never commit real credentials.

### Backend tests

```bash
cd backend
python -m pytest -q
```

### Frontend verification

```bash
cd frontend
npm ci
npm run lint
npm run build
```

## Continuous integration

GitHub Actions runs three independent lanes:

1. **Backend:** dependency install, full pytest suite and synthetic evaluation.
2. **Frontend:** npm install, TypeScript verification and production build.
3. **Docker:** Compose build, startup, `/health` verification and teardown.

### Latest verified CI snapshot

**2 October 2026**

- Backend: **152 tests passed**
- Synthetic fixture evaluation: **passed**
- Frontend TypeScript/lint: **passed**
- Frontend production build: **passed**
- Docker Compose build/start/health/teardown: **passed**

The backend suite still emits non-blocking collection/deprecation warnings.

## Evaluation

### Synthetic fixture benchmark

Current fixture evaluation reports:

- event-detection precision/recall/F1: **1.000**
- entity-link precision/recall/F1: **1.000**
- entity exact-decision accuracy: **0.833** on 6 labeled cases
- timeline fixture accuracy: **1.000**
- replay consistency: **1.000** across repeated runs

These are synthetic fixture results only. They are not real-world fraud-detection accuracy and are not evidence of product-market fit.

### DB-backed API regression

A visible DB-backed suite exercises the customer-style payout CSV path, including:

- clean imports;
- suspicious imports;
- malformed CSV rejection;
- replay/idempotency behavior;
- authentication and RBAC boundaries;
- merchant/incident ownership checks;
- recovery read-only behavior.

The repository currently contains **60 labeled customer-import regression cases** in addition to the broader backend suite.

## Production status

PRIMHORA is a **production-hardened capstone/product build with a live demo deployment**, not yet approved for unrestricted external customer financial data.

### Implemented

- deterministic financial incident scoring;
- source-backed incident reconstruction;
- tenant-scoped API access;
- RBAC;
- OIDC/JWT validation seam;
- evidence hashing and verification states;
- human attestations;
- graph and exposure computation;
- recovery-command state machine;
- read-only financial execution boundary;
- PDF evidence-packet export;
- generic payout CSV ingestion;
- Vercel + Render deployment topology;
- CI and Docker verification.

### Remaining production gates

- activate and operate a real production identity provider;
- complete durable organization/membership/invitation lifecycle;
- formalize evidence backup, retention and restore operations;
- complete the first customer-required provider integration;
- add distributed rate limiting and abuse controls;
- add product-level observability, request correlation, alerts and an incident runbook;
- keep production schema lifecycle migration-only;
- complete deployed-browser smoke verification;
- validate the workflow on real investigator/customer cases.

See [PRODUCTION_DISCREPANCIES.md](PRODUCTION_DISCREPANCIES.md) for the current gap register.

## What PRIMHORA does not claim

PRIMHORA does not claim:

- autonomous fraud decisions;
- live bank connectivity by default;
- a current Razorpay partnership;
- automatic financial recovery;
- successful recovery of funds;
- real-world fraud-detection precision/recall;
- product-market fit;
- customer savings that have not been measured;
- synthetic benchmark performance as a proxy for production performance.

Razorpay-shaped schema support and a provider adapter are implementation surfaces, not claims of partnership or live connection.

## Market evidence

The market research separates verified external evidence from founder assessment. See [docs/MARKET_EVIDENCE.md](docs/MARKET_EVIDENCE.md).

The current evidence supports a real financial-fraud and investigation problem, but it does not establish the size or willingness-to-pay of the specific PRIMHORA software category. Customer discovery must settle that.

## Documentation map

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System diagram, data model and deterministic services |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Product walkthrough and buyer-discovery script |
| [LIVE_INTEGRATIONS.md](LIVE_INTEGRATIONS.md) | Current integrations and deployment boundaries |
| [PRODUCTION_DISCREPANCIES.md](PRODUCTION_DISCREPANCIES.md) | Production gap register |
| [LIMITATIONS.md](LIMITATIONS.md) | Explicit product limitations |
| [AUDIT.md](AUDIT.md) | Engineering audit history |
| [FINAL_PASS_FAIL_SCORECARD.md](FINAL_PASS_FAIL_SCORECARD.md) | Verification status ledger |
| [docs/PRODUCTION_AUTH.md](docs/PRODUCTION_AUTH.md) | Production OIDC setup |

## Development principle

Do not make the product look more mature than the underlying evidence.

A green build is not customer validation.

A synthetic benchmark is not production accuracy.

A UI status is not a source-of-record fact.

And an AI explanation is not financial truth.

## FTX public-source validation

The repository now includes a real-world FTX-2022 validation corpus under `cases/FTX-2022/`.

The corpus is deliberately **document-grounded rather than synthetic transaction data**. It records public primary-source provenance from SEC enforcement complaints/releases and a U.S. Government Publishing Office congressional record, hashes the checked-in source metadata snapshots, and maps deterministic ground-truth anchors to their evidence.

Run:

```bash
cd backend
python -m app.evaluation.ftx_validation
```

The validator is part of CI. Current corpus targets are 100% source-hash integrity, 100% anchor-to-evidence coverage, and 0% unsupported anchors.

This is **not** a claim of complete FTX transaction reconstruction. Private customer ledgers, bank statements and exchange database exports are not publicly included in this corpus. PRIMHORA therefore preserves the distinction between public-source forensic validation and transaction-level reconstruction.
