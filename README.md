# Project: Keyword Check – Kobiga

## Purpose
Analyze eligible UK eBay SKU/Product data using the approved requirement and Keyword Analysis methodology, producing evidence-backed keyword and competitor analysis and a standalone HTML report.

## Scope principle
The database determines the eligible product population. The requirement defines the required output structure. The Keyword Analysis document defines the research methodology.

## Current state (2026-09-22)

| Field | Value |
|---|---|
| Scope | 12 approved Product IDs in `10_automation/scope.json` (v2), the only source of truth for eligibility |
| Automation | Daily at 08:45, same-day retries 10:45 / 12:45 / 14:45 (Windows task `KeywordCheckKobiga_Daily`); how it works: `10_automation/README.md` |
| Live dashboard | `07_report/keyword_check_kobiga.html` (last validated version; never hand-edited) |
| Status | Built, tested, scheduled. Live eBay research and the PH Dashboard push are not yet proven (see `08_handover/HANDOVER.md`) |
| Owner / requester | Kobiga |
| Governance | `Mini-AIOS_Master_Instruction_and_Skill_Guide (1).docx` |
| Next step | Check the 2026-09-23 08:45 run (`09_closure/CLOSURE_2026-09-22.md`) |

## Folder map (numbered in workflow order; one copy of everything)

```
Keyword_Check_Kobiga/
├── README.md              this index
├── 00_requirements/       requirement CSV + Keyword Analysis.pdf (approved sources, read-only)
├── 01_prompts/            PROMPT_LOG.md: the instructions that drove each phase
├── 02_source_mapping/     product_mapping/ (ID -> Sub-Type, Mapping Source) · keyword_mapping/ (ID -> Search Term) · population/
├── 03_sql/                the only DB queries (filtered by the approved IDs)
├── 04_research/           search_results/ · competitor_listings/ · descriptions/ · keyword_evidence/  (by date)
├── 05_evidence/           database/ (DB snapshots, PH publish log) · research_logs/ (logs, summaries, status) · screenshots/ · ebay/
├── 06_validation/         preflight / dry-run / local validation results per run
├── 07_report/             keyword_check_kobiga.html = live dashboard · .staging/ = pages awaiting or failing validation
├── 08_handover/           HANDOVER.md: status, evidence per claim, blockers, do-not-touch
├── 09_closure/            daily closure notes (Mini-AIOS 0.1 §11)
├── 10_automation/         pipeline code, scope.json, design, asset inventory, tests, scheduler, README
└── 11_archive/            YYYY/MM/DD/<run_id>/: immutable package per run (+ md5 manifest)
```

| Folder | Written by |
|---|---|
| `02_source_mapping/` | `map_products.py`. `population/` is *empty by design*: the population is the fixed list in `scope.json`. |
| `04_research/` | `research.py`. The `imported_2026-09-22/` sub-folders hold the history imported once from the old project by `import_history.py`. |
| `05_evidence/` | `run.py`, `publish.py`, `validate_dashboard.py`. `ebay/` is *empty by design*: eBay evidence lives in `04_research/`. |
| `06_validation/`, `07_report/`, `11_archive/` | `run.py`, `generate_dashboard.py`, `publish.py`, `archive.py` |
| `00_`, `01_`, `03_`, `08_`, `09_`, `10_` | people (reviewed changes only) |

## Structure history (2026-09-22)

- **Duplicate removed.** A full copy of the old project (`00_Requirements … 05_Validation`, 689 files, ~615 MB) had been placed in this folder at 15:49. Every file was md5-verified identical to the original, which remains untouched at `C:\Users\LED 222\Keywords check\` (the read-only legacy reference). The owner removed `00_Requirements` and `03_Report` at 15:56; the remaining four were removed at 16:00 on the owner's instruction.
- **Folders numbered** on the owner's instruction. All code paths are defined once in `10_automation/config.py` (`F = {...}`). The live state (`05_evidence/research_logs/research_status.json`, `last_success.json`, `04_research/**/*.json`) was rewritten to the new paths. The scheduled task was re-registered with `10_automation\run.py`, and the pipeline was re-tested (21/21 tests, dry run PASS, local run PASS).
- **Old path names in historical records.** Run records written **before** the rename keep their paths as written, because they are historical evidence and the archive md5 manifests must stay valid. This covers `11_archive/2026/09/22/*`, `06_validation/2026-09-22/*`, and run summaries and logs up to run `20260922T101640Z-f370`. In those records, read `evidence/…` as `05_evidence/…`, `research/…` as `04_research/…`, `report/…` as `07_report/…`, and so on, per the tree above.
