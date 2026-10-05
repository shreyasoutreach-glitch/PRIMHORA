"""Deterministic validation for the public-source FTX-2022 corpus.

This validator intentionally does not pretend that public complaints are a
transaction ledger. It validates provenance and document-grounded forensic
anchors, while preserving source confidence labels such as PRIMARY_SOURCE_ALLEGATION.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CASE_ROOT = ROOT.parent / "cases" / "FTX-2022"
MANIFEST = CASE_ROOT / "manifest" / "evidence_manifest.json"
ANCHORS = CASE_ROOT / "ground_truth" / "anchors.json"
SNAPSHOT_DIR = CASE_ROOT / "raw" / "source_metadata"

SOURCE_FILES = {
    "sec_sbf_complaint_2022_12_13": "sec_sbf_complaint_2022_12_13.json",
    "sec_ellison_wang_complaint_2022_12_21": "sec_ellison_wang_complaint_2022_12_21.json",
    "sec_singh_2023_02_28": "sec_singh_2023_02_28.json",
    "house_ftx_investigation_summary_2023_05_10": "house_ftx_investigation_summary_2023_05_10.json",
}


def validate() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))

    source_ids = set(manifest["sources"])
    if source_ids != set(SOURCE_FILES):
        raise AssertionError(f"source inventory mismatch: {sorted(source_ids)}")

    hashes_ok = 0
    for source_id, filename in SOURCE_FILES.items():
        path = SNAPSHOT_DIR / filename
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        expected = manifest["sources"][source_id]["snapshot_sha256"]
        if actual != expected:
            raise AssertionError(f"SHA-256 mismatch for {source_id}: {actual} != {expected}")
        hashes_ok += 1

    ids = [a["id"] for a in anchors]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate ground-truth anchor id")

    covered = 0
    unsupported = 0
    for anchor in anchors:
        evidence = anchor.get("evidence", [])
        if not evidence or not set(evidence).issubset(source_ids):
            unsupported += 1
            continue
        covered += 1

    coverage = covered / len(anchors) if anchors else 0.0
    unsupported_rate = unsupported / len(anchors) if anchors else 0.0
    result = {
        "case_id": manifest["case_id"],
        "validation_mode": manifest["validation_mode"],
        "sources": len(source_ids),
        "anchors": len(anchors),
        "evidence_hash_integrity": hashes_ok / len(source_ids) if source_ids else 0.0,
        "anchor_evidence_coverage": round(coverage, 3),
        "unsupported_anchor_rate": round(unsupported_rate, 3),
        "all_hashes_valid": hashes_ok == len(source_ids),
        "all_anchors_supported": unsupported == 0,
        "limitations": manifest["limitations"],
    }
    if not result["all_hashes_valid"] or not result["all_anchors_supported"]:
        raise AssertionError(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
