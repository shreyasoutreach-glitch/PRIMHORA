# PRIMHORA FTX-2022 Validation Corpus

## Purpose

This case validates PRIMHORA against **real public primary-source records** concerning the FTX collapse.

The corpus is deliberately scoped as a **document-grounded forensic validation**, not a fabricated transaction ledger. It tests whether PRIMHORA can preserve provenance, hash evidence, map claims to source artifacts, build deterministic entity/relationship/temporal anchors, and refuse to promote allegations into transaction-level financial truth.

## Primary sources

1. SEC, *SEC v. Samuel Bankman-Fried*, 1:22-cv-10501, filed December 13, 2022.
2. SEC, *SEC v. Caroline Ellison and Zixiao Wang*, 1:22-cv-10794, filed December 21, 2022.
3. SEC, *SEC v. Nishad Singh*, Litigation Release 25652, February 28, 2023.
4. U.S. Government Publishing Office / House committee record, *FTX Investigation Summary*, as of May 10, 2023.

The exact source URLs and retrieval metadata are in `manifest/evidence_manifest.json`.

## What is validated

- evidence metadata is immutable and SHA-256 addressable;
- every ground-truth anchor cites at least one primary source artifact;
- no anchor is accepted without source coverage;
- source classifications preserve the distinction between allegation and adjudicated fact;
- temporal, entity and software-control relationships are represented deterministically;
- the validator produces a reproducible report.

## What is not claimed

This corpus does **not** contain private FTX customer ledgers, exchange database dumps, bank statements, wallet-level forensic exports, or customer-level transaction history. It therefore does not support a claim of transaction-level precision/recall or complete reconstruction of FTX's financial books.

That boundary is intentional. PRIMHORA must never manufacture missing records merely to make a case look complete.

## Validation command

From `backend/`:

```bash
python -m app.evaluation.ftx_validation
```

The command validates the checked-in corpus and exits non-zero on hash mismatch, missing evidence, unsupported anchors, or duplicate anchor identifiers.
