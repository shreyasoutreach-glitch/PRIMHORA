"""
Production-shaped data model for PRIMHORA.

This is deliberately built around Razorpay's actual financial primitives
(Payments, RazorpayX Payouts, Contacts, Fund Accounts, Transfers, Settlements,
Events) rather than one generic "transaction" table, per the architecture doc.

Every table that can be pointed at from a claim, a graph edge, or a recovery
packet line has a stable string ID (not just an autoincrement PK) so that
evidence, audit events, and the frontend can all refer to "PYO_..." /
"FA_..." the way a real integration would.

MULTI-TENANCY: every table below except `Tenant` itself inherits `TenantScoped`,
which adds a required `tenant_id` column. Enforcement is NOT "remember to add
.filter(tenant_id=...) everywhere" -- it is structural, via `TenantScopedSession`
in app/core/tenancy.py, which overrides Session.get()/query()/add() so tenant
filtering happens automatically for any code that uses the normal Session API.
See app/core/tenancy.py's docstring for exactly what is and isn't covered.
"""
from __future__ import annotations

import datetime as dt

from decimal import Decimal
from sqlalchemy import (
    Numeric,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    Index,
    Integer,
    LargeBinary,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

from sqlalchemy.types import TypeDecorator, JSON
from app.core.serialization import to_json_safe

class SafeJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return to_json_safe(value)
        return value

    def process_result_value(self, value, dialect):
        return value




def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class TenantScoped:
    """Mixin for every row that belongs to exactly one tenant. Combined with
    TenantScopedSession, this is what makes cross-tenant access fail closed
    by default rather than relying on every query author remembering a
    filter."""

    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id"), index=True, nullable=False
    )


class Tenant(Base):
    """A FIRST HOUR customer -- in the real target market, a payments
    platform/bank/BaaS provider, each with many merchants underneath it.
    Deliberately the ONLY table with no tenant_id of its own."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Core Razorpay-shaped financial primitives
# ---------------------------------------------------------------------------


class Merchant(Base, TenantScoped):
    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_merchants_tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), default="general")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    is_flagship: Mapped[bool] = mapped_column(Boolean, default=False)


class Employee(Base, TenantScoped):
    """An employee/communication-account holder at a merchant. This is the
    node that a compromised-account incident actually happens to."""

    __tablename__ = "employees"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_employees_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(80), default="finance_ops")
    comm_handle: Mapped[str] = mapped_column(String(120))  # e.g. WhatsApp/phone identity
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Order(Base, TenantScoped):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_orders_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_orders_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    status: Mapped[str] = mapped_column(String(24), default="paid")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Payment(Base, TenantScoped):
    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_payments_tenant_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_payments_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(32), index=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    customer_id: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    status: Mapped[str] = mapped_column(String(24), default="captured")
    method: Mapped[str] = mapped_column(String(24), default="upi")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Contact(Base, TenantScoped):
    """A RazorpayX Contact -- the human/entity a payout is made to."""

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_contacts_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_contacts_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(24), default="vendor")  # vendor/employee/customer
    phone: Mapped[str] = mapped_column(String(24), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    upi_id: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class FundAccount(Base, TenantScoped):
    __tablename__ = "fund_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fund_accounts_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_fund_accounts_tenant_contact",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    contact_id: Mapped[str] = mapped_column(String(32), index=True)
    account_type: Mapped[str] = mapped_column(String(16), default="bank_account")  # or vpa
    masked_bank_account: Mapped[str] = mapped_column(String(40), default="")
    masked_ifsc: Mapped[str] = mapped_column(String(20), default="")
    vpa: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Payout(Base, TenantScoped):
    __tablename__ = "payouts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_payouts_tenant_merchant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_payouts_tenant_contact",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "fund_account_id"],
            ["fund_accounts.tenant_id", "fund_accounts.id"],
            name="fk_payouts_tenant_fund_account",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    contact_id: Mapped[str] = mapped_column(String(32), index=True)
    fund_account_id: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    purpose: Mapped[str] = mapped_column(String(40), default="vendor_bill")
    mode: Mapped[str] = mapped_column(String(16), default="IMPS")
    narration: Mapped[str] = mapped_column(String(200), default="")
    reference_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="processed", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)

    is_injected: Mapped[bool] = mapped_column(Boolean, default=False)


class Transfer(Base, TenantScoped):
    """Route/linked-account transfer."""

    __tablename__ = "transfers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_transfers_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    source_payment_id: Mapped[str] = mapped_column(String(32), default="")
    destination_account_id: Mapped[str] = mapped_column(String(32), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    status: Mapped[str] = mapped_column(String(24), default="processed")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Settlement(Base, TenantScoped):
    __tablename__ = "settlements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_settlements_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    status: Mapped[str] = mapped_column(String(24), default="processed")
    settlement_window_start: Mapped[dt.datetime] = mapped_column(DateTime)
    settlement_window_end: Mapped[dt.datetime] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class FinancialEvent(Base, TenantScoped):
    """The canonical event model from the architecture doc -- every payment,
    payout, transfer and settlement also gets normalized into one of these so
    the incident engine, graph and audit trail all read from one place."""

    __tablename__ = "financial_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_financial_events_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_financial_events_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)  # payment/payout/transfer/settlement
    source_system: Mapped[str] = mapped_column(String(32), default="razorpay")
    source_record_id: Mapped[str] = mapped_column(String(32), index=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[str] = mapped_column(String(32), default="")  # employee/system actor
    account_id: Mapped[str] = mapped_column(String(32), default="")
    counterparty_id: Mapped[str] = mapped_column(String(32), default="", index=True)  # contact id
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    attributes: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    evidence_refs: Mapped[list] = mapped_column(SafeJSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    extraction_method: Mapped[str] = mapped_column(String(32), default="system_of_record")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class WebhookEvent(Base, TenantScoped):
    __tablename__ = "webhook_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_webhook_events_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    source_object_type: Mapped[str] = mapped_column(String(32))
    source_object_id: Mapped[str] = mapped_column(String(32), index=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


# ---------------------------------------------------------------------------
# Evidence + extraction
# ---------------------------------------------------------------------------


class EvidenceArtifact(Base, TenantScoped):
    __tablename__ = "evidence_artifacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evidence_artifacts_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_evidence_artifacts_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_label: Mapped[str] = mapped_column(String(40), default="upload")  # whatsapp/sms/bank/email
    raw_text: Mapped[str] = mapped_column(Text, default="")
    content_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ExtractedClaim(Base, TenantScoped):
    __tablename__ = "extracted_claims"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "source_artifact_id"],
            ["evidence_artifacts.tenant_id", "evidence_artifacts.id"],
            name="fk_extracted_claims_tenant_artifact",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_artifact_id: Mapped[str] = mapped_column(String(40), index=True)
    source_location: Mapped[str] = mapped_column(String(120), default="")
    extraction_method: Mapped[str] = mapped_column(String(40), default="rule_based_extractor")
    claim_type: Mapped[str] = mapped_column(String(40))  # instruction/amount/beneficiary/timestamp
    claim_value: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    verification_status: Mapped[str] = mapped_column(String(24), default="UNVERIFIED", index=True)
    matched_financial_event_id: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class CommunicationEvent(Base, TenantScoped):
    __tablename__ = "communication_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "source_artifact_id"],
            ["evidence_artifacts.tenant_id", "evidence_artifacts.id"],
            name="fk_communication_events_tenant_artifact",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_artifact_id: Mapped[str] = mapped_column(String(40), index=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    sender_label: Mapped[str] = mapped_column(String(120))
    channel: Mapped[str] = mapped_column(String(24), default="whatsapp")
    body_text: Mapped[str] = mapped_column(Text)
    mentioned_amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    mentioned_beneficiary_text: Mapped[str] = mapped_column(String(160), default="")
    resolved_contact_id: Mapped[str] = mapped_column(String(32), default="")
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    correlation_status: Mapped[str] = mapped_column(String(24), default="UNCORRELATED")  # CORROBORATED/POSSIBLE
    correlated_financial_event_id: Mapped[str] = mapped_column(String(40), default="")


class EntityLink(Base, TenantScoped):
    """Result of entity resolution between two records (e.g. a communication
    mention and a Contact, or two Contacts suspected to be the same entity)."""

    __tablename__ = "entity_links"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    left_type: Mapped[str] = mapped_column(String(32))
    left_id: Mapped[str] = mapped_column(String(64), index=True)
    right_type: Mapped[str] = mapped_column(String(32))
    right_id: Mapped[str] = mapped_column(String(64), index=True)
    signal: Mapped[str] = mapped_column(String(40))  # exact_transaction_id / normalized_name / ...
    weight: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(16))  # AUTO_LINK / REVIEW / KEEP_SEPARATE
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Incident, human context, audit
# ---------------------------------------------------------------------------


class Incident(Base, TenantScoped):
    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_incidents_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "merchant_id"],
            ["merchants.tenant_id", "merchants.id"],
            name="fk_incidents_tenant_merchant",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(32), default="INGESTING", index=True)
    scenario: Mapped[str] = mapped_column(String(48), default="")
    incident_evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_components: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    window_start: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(24), default="v1")
    config_version: Mapped[str] = mapped_column(String(24), default="v1")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    # Enterprise incident-state fields (Section 1 of the enterprise brief).
    # These are populated by services/incident/detector.py; several are
    # deliberately duplicative of score_components/exposure so a caller can
    # get incident-level headline facts without a second round trip.
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")  # LOW/MEDIUM/HIGH/CRITICAL
    financial_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    recoverable_amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    unrecoverable_amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_entities: Mapped[int] = mapped_column(Integer, default=0)
    resolution_state: Mapped[str] = mapped_column(String(24), default="OPEN")  # OPEN/RESOLVED/ESCALATED


class IncidentEvent(Base, TenantScoped):
    """A financial_event that has been pulled into a specific incident's case
    file (the payouts on the incident spine)."""

    __tablename__ = "incident_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "incident_id"],
            ["incidents.tenant_id", "incidents.id"],
            name="fk_incident_events_tenant_incident",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "financial_event_id"],
            ["financial_events.tenant_id", "financial_events.id"],
            name="fk_incident_events_tenant_financial_event",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True)
    financial_event_id: Mapped[str] = mapped_column(String(40), index=True)
    role: Mapped[str] = mapped_column(String(32), default="suspicious_payout")
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class HumanAttestation(Base, TenantScoped):
    __tablename__ = "human_attestations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "incident_id"],
            ["incidents.tenant_id", "incidents.id"],
            name="fk_human_attestations_tenant_incident",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    question_text: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(String(16))  # YES/NO/NOT_SURE
    note: Mapped[str] = mapped_column(String(500), default="")
    actor: Mapped[str] = mapped_column(String(80), default="merchant_user")
    affected_predicate: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AuditEvent(Base, TenantScoped):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    actor: Mapped[str] = mapped_column(String(16), default="SYSTEM")  # SYSTEM / HUMAN
    actor_user_id: Mapped[str] = mapped_column(String(32), default="")  # set when actor == HUMAN
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    summary: Mapped[str] = mapped_column(String(300), default="")
    sources: Mapped[list] = mapped_column(SafeJSON, default=list)
    detail: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    before_state: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    after_state: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class User(Base, TenantScoped):
    """Application identity binding for Primhora RBAC.

    Passwords and identity-provider credentials do not live in this database.
    Production requests are authenticated by the configured OIDC provider and
    mapped to this row through the immutable idp_subject claim. The
    api_token column remains only for legacy/demo compatibility and is not
    accepted by the production authentication path."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(160))
    # Immutable subject from the configured OIDC identity provider. Nullable only
    # for legacy/demo rows; production authentication requires this mapping.
    idp_subject: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(24), index=True)  # ANALYST/INVESTIGATOR/FINANCE_OPERATOR/APPROVER/ADMINISTRATOR
    api_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Recovery commands (Section 4 of the enterprise brief)
# ---------------------------------------------------------------------------


class RecoveryCommand(Base, TenantScoped):
    """A structured, auditable recovery action -- separate from the Recovery
    Packet (which is a read-only document). This is what gets proposed,
    approved, dry-run, and (simulated-)executed, with a real state machine
    and idempotency guarantee. See services/recovery/command.py."""

    __tablename__ = "recovery_commands"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "incident_id"],
            ["incidents.tenant_id", "incidents.id"],
            name="fk_recovery_commands_tenant_incident",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(40))  # e.g. FREEZE_PAYOUT / REVERSE_EVENT / LEDGER_CORRECTION
    target_type: Mapped[str] = mapped_column(String(32))  # payout / fund_account / ledger_entry
    target_id: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    reason: Mapped[str] = mapped_column(String(400), default="")
    supporting_evidence: Mapped[list] = mapped_column(SafeJSON, default=list)  # artifact/claim/event IDs
    expected_effect: Mapped[str] = mapped_column(String(400), default="")
    risk: Mapped[str] = mapped_column(String(16), default="MEDIUM")  # LOW/MEDIUM/HIGH
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    required_approval_role: Mapped[str] = mapped_column(String(24), default="APPROVER")
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    state: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    # PROPOSED -> REVIEWED -> APPROVED -> EXECUTED -> VERIFIED, or -> REJECTED

    created_by: Mapped[str] = mapped_column(String(32))  # users.id
    reviewed_by: Mapped[str] = mapped_column(String(32), default="")
    approved_by: Mapped[str] = mapped_column(String(32), default="")
    executed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(16), default="")  # SIMULATED / EXECUTED
    dry_run_result: Mapped[dict] = mapped_column(SafeJSON, default=dict)
    execution_result: Mapped[dict] = mapped_column(SafeJSON, default=dict)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


Index("ix_payout_merchant_created", Payout.merchant_id, Payout.created_at)
Index("ix_fevent_merchant_ts", FinancialEvent.merchant_id, FinancialEvent.timestamp)
Index("ix_payout_tenant", Payout.tenant_id)
Index("ix_incident_tenant", Incident.tenant_id)
