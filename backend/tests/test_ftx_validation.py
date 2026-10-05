from app.evaluation.ftx_validation import validate


def test_ftx_public_source_corpus_is_intact():
    result = validate()
    assert result["all_hashes_valid"] is True
    assert result["all_anchors_supported"] is True
    assert result["evidence_hash_integrity"] == 1.0
    assert result["anchor_evidence_coverage"] == 1.0
    assert result["unsupported_anchor_rate"] == 0.0
