from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.audit.logger import log as audit_log
from app.core.authz import get_tenant_db, require_permission
from app.core.config import get_settings
from app.models import entities as m
from app.services.evidence.pipeline import (
    cross_reference_amount_claim,
    extract_candidate_claims,
    is_path_contained,
    safe_filename,
    sha256_bytes,
    validate_mime,
)

router = APIRouter(tags=["evidence"])
settings = get_settings()


def _stored_path(artifact: m.EvidenceArtifact, tenant_id: str) -> str:
    return os.path.join(
        settings.evidence_storage_dir,
        f"tenant_{tenant_id}",
        f"{artifact.id}_{artifact.filename}",
    )


def _extract_pdf_text(data: bytes) -> str:
    try:
        from io import BytesIO
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception:
        return ""


def _binary_evidence_extraction(
    data: bytes,
    mime_type: str,
    artifact_id: str,
) -> tuple[str, list[dict]]:
    """Real extraction for images/scanned PDFs when GEMINI_API_KEY is configured.

    No model output is marked verified here. It is only converted into candidate
    claims and later cross-referenced against the canonical financial events.
    """
    from app.services.evidence.provider import GeminiEvidenceProvider

    provider = GeminiEvidenceProvider(api_key=settings.gemini_api_key or None)
    return provider.extract_binary(data, mime_type, artifact_id)


@router.post("/evidence/upload")
async def upload_evidence(
    file: UploadFile,
    merchant_id: str = Form(...),
    incident_id: str = Form(""),
    source_label: str = Form("upload"),
    db: Session = Depends(get_tenant_db),
    _user: m.User = Depends(require_permission("INVESTIGATE")),
):
    if settings.demo_mode and not settings.demo_allow_external_ingestion:
        raise HTTPException(
            403,
            "External evidence uploads are disabled while the shared demo identity is active. "
            "Configure production OIDC and disable DEMO_MODE before accepting customer evidence.",
        )
    merchant = db.get(m.Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(404, "merchant not found")
    if incident_id:
        incident = db.get(m.Incident, incident_id)
        if incident is None or incident.merchant_id != merchant_id:
            raise HTTPException(404, "incident not found for merchant")

    data = await file.read(settings.max_evidence_bytes + 1)
    if len(data) > settings.max_evidence_bytes:
        raise HTTPException(413, f"Evidence file exceeds the {settings.max_evidence_bytes // (1024 * 1024)} MB limit")
    mime_type = file.content_type or "application/octet-stream"
    if not validate_mime(mime_type):
        raise HTTPException(400, f"Unsupported MIME type: {mime_type}")

    digest = sha256_bytes(data)
    tenant_dir = os.path.join(settings.evidence_storage_dir, f"tenant_{_user.tenant_id}")
    os.makedirs(tenant_dir, exist_ok=True)
    artifact_id = f"EVD_{uuid.uuid4().hex[:10]}"

    display_filename = safe_filename(file.filename)
    stored_path = os.path.join(tenant_dir, f"{artifact_id}_{display_filename}")
    if not is_path_contained(tenant_dir, stored_path):
        raise HTTPException(400, "Invalid filename.")

    with open(stored_path, "wb") as f:
        f.write(data)

    raw_text = ""
    extraction_status = "queued_for_vision_extraction"
    if mime_type.startswith("text/"):
        raw_text = data.decode("utf-8", errors="ignore")
        extraction_status = "text_ready"
    elif mime_type == "application/pdf":
        raw_text = _extract_pdf_text(data)
        if raw_text:
            extraction_status = "text_ready"

    artifact = m.EvidenceArtifact(
        id=artifact_id,
        incident_id=incident_id,
        merchant_id=merchant_id,
        filename=display_filename,
        mime_type=mime_type,
        sha256=digest,
        source_label=source_label,
        raw_text=raw_text,
        content_bytes=data,
        extraction_status=extraction_status,
    )
    db.add(artifact)
    audit_log(
        db,
        incident_id=incident_id,
        actor="SYSTEM",
        event_type="EVIDENCE_UPLOADED",
        summary=f"{display_filename} ({digest[:12]}...)",
        sources=[artifact_id],
        detail={"mime_type": mime_type, "extraction_status": extraction_status},
    )
    db.commit()

    return {
        "artifact_id": artifact.id,
        "filename": artifact.filename,
        "sha256": artifact.sha256,
        "mime_type": artifact.mime_type,
        "extraction_status": artifact.extraction_status,
        "vision_available": bool(settings.gemini_api_key),
    }


@router.post("/evidence/analyze")
def analyze_evidence(
    artifact_id: str = Form(...),
    db: Session = Depends(get_tenant_db),
    _user: m.User = Depends(require_permission("INVESTIGATE")),
):
    artifact = db.get(m.EvidenceArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "artifact not found")

    if artifact.extraction_status == "queued_for_vision_extraction":
        if not settings.gemini_api_key:
            raise HTTPException(
                503,
                "This image/scanned PDF needs GEMINI_API_KEY for real multimodal extraction. "
                "The artifact was stored and hashed, but no claims are fabricated.",
            )

        try:
            if artifact.content_bytes is not None:
                data = artifact.content_bytes
            else:
                with open(_stored_path(artifact, _user.tenant_id), "rb") as handle:
                    data = handle.read()
            extracted_text, candidates = _binary_evidence_extraction(
                data, artifact.mime_type, artifact.id
            )
            artifact.raw_text = extracted_text
        except Exception as exc:
            artifact.extraction_status = "extraction_failed"
            db.rollback()
            raise HTTPException(502, "Vision extraction failed. The evidence remains stored and unverified.") from exc
    else:
        candidates = extract_candidate_claims(artifact.raw_text, artifact.id)

    # Re-analysis is idempotent: replace prior candidate claims for this artifact
    # instead of silently duplicating them.
    db.query(m.ExtractedClaim).filter(
        m.ExtractedClaim.source_artifact_id == artifact.id
    ).delete(synchronize_session=False)

    financial_events = (
        db.query(m.FinancialEvent)
        .filter(m.FinancialEvent.merchant_id == artifact.merchant_id)
        .all()
    )
    candidate_events = [(fe.id, fe.amount) for fe in financial_events]

    verified_count = conflicting_count = unverified_count = 0
    for c in candidates:
        status = "UNVERIFIED"
        matched = ""
        if c["claim_type"] == "amount":
            status, matched = cross_reference_amount_claim(
                c["claim_value"]["amount"], candidate_events
            )
        if status == "VERIFIED":
            verified_count += 1
        elif status == "CONFLICTING":
            conflicting_count += 1
        else:
            unverified_count += 1

        db.add(
            m.ExtractedClaim(
                id=c["id"],
                source_artifact_id=c["source_artifact_id"],
                source_location=c["source_location"],
                extraction_method=c["extraction_method"],
                claim_type=c["claim_type"],
                claim_value=c["claim_value"],
                verification_status=status,
                matched_financial_event_id=matched,
            )
        )

    artifact.extraction_status = "extracted"
    audit_log(
        db,
        incident_id=artifact.incident_id,
        actor="SYSTEM",
        event_type="EVIDENCE_ANALYZED",
        summary=f"{len(candidates)} candidate claims extracted from {artifact.filename}",
        sources=[artifact.id],
        detail={
            "verified": verified_count,
            "conflicting": conflicting_count,
            "unverified": unverified_count,
        },
    )
    db.commit()

    return {
        "artifact_id": artifact.id,
        "claims": candidates,
        "verification_summary": {
            "verified": verified_count,
            "conflicting": conflicting_count,
            "unverified": unverified_count,
        },
    }
