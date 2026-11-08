"""Enforce same-tenant references with composite foreign keys.

Revision ID: f3a8d1c6e9b2
Revises: e7f1c9a4b2d6

The migration fails closed if any existing reference crosses tenant
boundaries. A live read-only audit on 2026-11-08 found zero mismatches across
all 21 tenant-to-tenant foreign-key relationships.
"""
from alembic import op

revision = "f3a8d1c6e9b2"
down_revision = "e7f1c9a4b2d6"
branch_labels = None
depends_on = None


_RELATIONSHIPS = (
    ("communication_events", "source_artifact_id", "evidence_artifacts"),
    ("contacts", "merchant_id", "merchants"),
    ("employees", "merchant_id", "merchants"),
    ("evidence_artifacts", "merchant_id", "merchants"),
    ("extracted_claims", "source_artifact_id", "evidence_artifacts"),
    ("financial_events", "merchant_id", "merchants"),
    ("fund_accounts", "contact_id", "contacts"),
    ("human_attestations", "incident_id", "incidents"),
    ("incident_events", "financial_event_id", "financial_events"),
    ("incident_events", "incident_id", "incidents"),
    ("incidents", "merchant_id", "merchants"),
    ("orders", "merchant_id", "merchants"),
    ("payments", "merchant_id", "merchants"),
    ("payments", "order_id", "orders"),
    ("payouts", "contact_id", "contacts"),
    ("payouts", "fund_account_id", "fund_accounts"),
    ("payouts", "merchant_id", "merchants"),
    ("recovery_commands", "incident_id", "incidents"),
    ("settlements", "merchant_id", "merchants"),
    ("transfers", "merchant_id", "merchants"),
    ("webhook_events", "merchant_id", "merchants"),
)

_FKS = (
    ("communication_events", "fk_communication_events_tenant_artifact", "source_artifact_id", "evidence_artifacts", "communication_events_source_artifact_id_fkey"),
    ("contacts", "fk_contacts_tenant_merchant", "merchant_id", "merchants", "contacts_merchant_id_fkey"),
    ("employees", "fk_employees_tenant_merchant", "merchant_id", "merchants", "employees_merchant_id_fkey"),
    ("evidence_artifacts", "fk_evidence_artifacts_tenant_merchant", "merchant_id", "merchants", "evidence_artifacts_merchant_id_fkey"),
    ("extracted_claims", "fk_extracted_claims_tenant_artifact", "source_artifact_id", "evidence_artifacts", "extracted_claims_source_artifact_id_fkey"),
    ("financial_events", "fk_financial_events_tenant_merchant", "merchant_id", "merchants", "financial_events_merchant_id_fkey"),
    ("fund_accounts", "fk_fund_accounts_tenant_contact", "contact_id", "contacts", "fund_accounts_contact_id_fkey"),
    ("human_attestations", "fk_human_attestations_tenant_incident", "incident_id", "incidents", "human_attestations_incident_id_fkey"),
    ("incident_events", "fk_incident_events_tenant_financial_event", "financial_event_id", "financial_events", "incident_events_financial_event_id_fkey"),
    ("incident_events", "fk_incident_events_tenant_incident", "incident_id", "incidents", "incident_events_incident_id_fkey"),
    ("incidents", "fk_incidents_tenant_merchant", "merchant_id", "merchants", "incidents_merchant_id_fkey"),
    ("orders", "fk_orders_tenant_merchant", "merchant_id", "merchants", "orders_merchant_id_fkey"),
    ("payments", "fk_payments_tenant_merchant", "merchant_id", "merchants", "payments_merchant_id_fkey"),
    ("payments", "fk_payments_tenant_order", "order_id", "orders", "payments_order_id_fkey"),
    ("payouts", "fk_payouts_tenant_contact", "contact_id", "contacts", "payouts_contact_id_fkey"),
    ("payouts", "fk_payouts_tenant_fund_account", "fund_account_id", "fund_accounts", "payouts_fund_account_id_fkey"),
    ("payouts", "fk_payouts_tenant_merchant", "merchant_id", "merchants", "payouts_merchant_id_fkey"),
    ("recovery_commands", "fk_recovery_commands_tenant_incident", "incident_id", "incidents", "recovery_commands_incident_id_fkey"),
    ("settlements", "fk_settlements_tenant_merchant", "merchant_id", "merchants", "settlements_merchant_id_fkey"),
    ("transfers", "fk_transfers_tenant_merchant", "merchant_id", "merchants", "transfers_merchant_id_fkey"),
    ("webhook_events", "fk_webhook_events_tenant_merchant", "merchant_id", "merchants", "webhook_events_merchant_id_fkey"),
)

_PARENT_UNIQUES = (
    ("merchants", "uq_merchants_tenant_id"),
    ("orders", "uq_orders_tenant_id"),
    ("contacts", "uq_contacts_tenant_id"),
    ("fund_accounts", "uq_fund_accounts_tenant_id"),
    ("financial_events", "uq_financial_events_tenant_id"),
    ("evidence_artifacts", "uq_evidence_artifacts_tenant_id"),
    ("incidents", "uq_incidents_tenant_id"),
)


def upgrade() -> None:
    # Preflight every relationship before any constraint is changed. This
    # protects existing data and makes the migration safe to abort atomically.
    op.execute(
        """
        DO $$
        DECLARE
            item record;
            mismatch_count bigint;
        BEGIN
            FOR item IN
                SELECT * FROM (VALUES
                    ('communication_events', 'source_artifact_id', 'evidence_artifacts'),
                    ('contacts', 'merchant_id', 'merchants'),
                    ('employees', 'merchant_id', 'merchants'),
                    ('evidence_artifacts', 'merchant_id', 'merchants'),
                    ('extracted_claims', 'source_artifact_id', 'evidence_artifacts'),
                    ('financial_events', 'merchant_id', 'merchants'),
                    ('fund_accounts', 'contact_id', 'contacts'),
                    ('human_attestations', 'incident_id', 'incidents'),
                    ('incident_events', 'financial_event_id', 'financial_events'),
                    ('incident_events', 'incident_id', 'incidents'),
                    ('incidents', 'merchant_id', 'merchants'),
                    ('orders', 'merchant_id', 'merchants'),
                    ('payments', 'merchant_id', 'merchants'),
                    ('payments', 'order_id', 'orders'),
                    ('payouts', 'contact_id', 'contacts'),
                    ('payouts', 'fund_account_id', 'fund_accounts'),
                    ('payouts', 'merchant_id', 'merchants'),
                    ('recovery_commands', 'incident_id', 'incidents'),
                    ('settlements', 'merchant_id', 'merchants'),
                    ('transfers', 'merchant_id', 'merchants'),
                    ('webhook_events', 'merchant_id', 'merchants')
                ) AS relations(child_table, child_column, parent_table)
            LOOP
                EXECUTE format(
                    'SELECT count(*) FROM public.%I child '
                    'JOIN public.%I parent ON child.%I = parent.id '
                    'WHERE child.tenant_id IS DISTINCT FROM parent.tenant_id',
                    item.child_table,
                    item.parent_table,
                    item.child_column
                ) INTO mismatch_count;

                IF mismatch_count > 0 THEN
                    RAISE EXCEPTION
                        'Refusing tenant FK migration: % cross-tenant references in %.%',
                        mismatch_count,
                        item.child_table,
                        item.child_column;
                END IF;
            END LOOP;
        END
        $$;
        """
    )

    for table, constraint in _PARENT_UNIQUES:
        op.execute(
            f'ALTER TABLE public.{table} ADD CONSTRAINT {constraint} UNIQUE (tenant_id, id)'
        )

    # Add and validate the stronger constraints before dropping the original
    # ID-only FKs. NOT VALID avoids an initial full-table scan while the new
    # constraint is installed; VALIDATE then proves all existing rows comply.
    for child, constraint, column, parent, old_constraint in _FKS:
        op.execute(
            f"ALTER TABLE public.{child} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY (tenant_id, {column}) "
            f"REFERENCES public.{parent} (tenant_id, id) NOT VALID"
        )
        op.execute(
            f"ALTER TABLE public.{child} VALIDATE CONSTRAINT {constraint}"
        )

    for child, constraint, column, parent, old_constraint in _FKS:
        op.execute(
            f"ALTER TABLE public.{child} DROP CONSTRAINT {old_constraint}"
        )


def downgrade() -> None:
    for child, constraint, column, parent, old_constraint in reversed(_FKS):
        op.execute(
            f"ALTER TABLE public.{child} DROP CONSTRAINT {constraint}"
        )
        op.execute(
            f"ALTER TABLE public.{child} ADD CONSTRAINT {old_constraint} "
            f"FOREIGN KEY ({column}) REFERENCES public.{parent} (id)"
        )

    for table, constraint in reversed(_PARENT_UNIQUES):
        op.execute(
            f"ALTER TABLE public.{table} DROP CONSTRAINT {constraint}"
        )
