"""Harden exposed production tables with RLS and foreign-key indexes.

Revision ID: d6f4a2b8c1e0
Revises: b4d2e8f1a7c9
"""

from alembic import op

revision = "d6f4a2b8c1e0"
down_revision = "b4d2e8f1a7c9"
branch_labels = None
depends_on = None

TABLES = [
    "alembic_version",
    "account_trust_states",
    "audit_events",
    "communication_events",
    "contacts",
    "employees",
    "entity_links",
    "evidence_artifacts",
    "extracted_claims",
    "financial_events",
    "fund_accounts",
    "graph_relationships",
    "human_attestations",
    "incident_events",
    "incidents",
    "merchants",
    "orders",
    "payments",
    "payouts",
    "recovery_commands",
    "risk_decisions",
    "risk_events",
    "settlements",
    "tenants",
    "transfers",
    "users",
    "webhook_events",
]

FOREIGN_KEYS = [
    ("audit_events", "tenant_id"),
    ("communication_events", "source_artifact_id"),
    ("communication_events", "tenant_id"),
    ("contacts", "tenant_id"),
    ("contacts", "merchant_id"),
    ("employees", "tenant_id"),
    ("employees", "merchant_id"),
    ("entity_links", "tenant_id"),
    ("evidence_artifacts", "merchant_id"),
    ("evidence_artifacts", "tenant_id"),
    ("extracted_claims", "source_artifact_id"),
    ("extracted_claims", "tenant_id"),
    ("financial_events", "tenant_id"),
    ("financial_events", "merchant_id"),
    ("fund_accounts", "tenant_id"),
    ("fund_accounts", "contact_id"),
    ("human_attestations", "incident_id"),
    ("human_attestations", "tenant_id"),
    ("incident_events", "incident_id"),
    ("incident_events", "tenant_id"),
    ("incident_events", "financial_event_id"),
    ("incidents", "merchant_id"),
    ("incidents", "tenant_id"),
    ("merchants", "tenant_id"),
    ("orders", "merchant_id"),
    ("orders", "tenant_id"),
    ("payments", "merchant_id"),
    ("payments", "order_id"),
    ("payments", "tenant_id"),
    ("payouts", "contact_id"),
    ("payouts", "fund_account_id"),
    ("payouts", "merchant_id"),
    ("payouts", "tenant_id"),
    ("recovery_commands", "incident_id"),
    ("recovery_commands", "tenant_id"),
    ("settlements", "merchant_id"),
    ("settlements", "tenant_id"),
    ("transfers", "merchant_id"),
    ("transfers", "tenant_id"),
    ("users", "tenant_id"),
    ("webhook_events", "merchant_id"),
    ("webhook_events", "tenant_id"),
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
    for table, column in FOREIGN_KEYS:
        op.execute(
            f'CREATE INDEX IF NOT EXISTS "{table}_{column}_idx" '
            f'ON public."{table}" ("{column}")'
        )


def downgrade() -> None:
    for table, column in reversed(FOREIGN_KEYS):
        op.execute(f'DROP INDEX IF EXISTS public."{table}_{column}_idx"')
    for table in reversed(TABLES):
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
