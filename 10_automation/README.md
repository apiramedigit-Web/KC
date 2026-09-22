# Keyword Check – Kobiga: Daily Automation

| Field | Value |
|---|---|
| What | A daily automated Keyword Check for the approved eBay UK Product IDs. It reads the live database, researches UK eBay competitors (Keyword Analysis.pdf), calculates keywords and Keyword Rank, builds a standalone HTML dashboard, validates it, publishes it locally, then pushes it to the PH Dashboard. |
| Schedule | Windows Task Scheduler task `KeywordCheckKobiga_Daily`, **daily at 08:45** local time |
| Live dashboard | `07_report/keyword_check_kobiga.html` (the last version that passed validation) |
| Scope | `10_automation/scope.json`: 12 approved Product IDs, the **only** source of truth |
| Design | `10_automation/WORKFLOW_DESIGN.md` · asset reuse: `10_automation/asset_inventory.md` · handover: `08_handover/HANDOVER.md` |
| Status | Built and tested 2026-09-22. First scheduled run: 2026-09-23 08:45. |

## 1. How to run

```powershell
python 10_automation\run.py                  # full daily run (this is what the scheduler runs)
python 10_automation\run.py --preflight      # checks only: scope, DB, 12-ID verification, browser, PH credentials
python 10_automation\run.py --dry-run        # DB read + build + validate in staging; no browser, no status change, no publish
python 10_automation\run.py --as-of 2026-09-23   # full run filed under that date (the DB is still read live)
python 10_automation\run.py --no-research    # skip eBay; rows show last verified evidence, labelled CARRIED FORWARD
python 10_automation\run.py --no-ph          # everything except the PH Dashboard push
python 10_automation\test_automation.py      # 21 offline tests
powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1            # register/update the 08:45 task
powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Status    # next run time
powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Unregister
```

Exit codes: `0` success (incl. carried-forward rows, preflight/dry-run OK) · `2` PH publish failed (local dashboard is updated) · `3` another run is already running · `1` anything else.

## 2. What must be in place at 08:45

| Need | Why | If missing |
|---|---|---|
| Logged-on Windows user | The task runs in the user session (the UK-VPN Chrome lives there) | Task starts when the user is next available |
| `WLP_SOURCE_DB_URL` (user env var, already set) | Read-only source database | Run stops: `PREFLIGHT_FAILED`; dashboards unchanged |
| **UK-VPN Chrome with remote debugging on `127.0.0.1:9222`**, exit country GB | eBay research (Keyword Analysis.pdf Step 1) | Research marked `FAILED` (retried next run); dashboard rows show the last verified evidence as **CARRIED FORWARD from date** |
| **`PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD`** (user env vars, *not set yet*) | PH Dashboard push | Run status `PUBLISH_FAILED`; the local dashboard is still updated; the push is retried next run |

## 3. Where the data comes from and what is eligible

- **Eligibility = the list in `scope.json`.** Nothing is discovered from the database. To change the scope, edit `product_ids`, raise `version`, and fill `change_note`. `rejected_product_ids` lists IDs that must never be used (`267765726284`).
- The DB is queried with `03_sql/fetch_listings.sql` (parent + variation rows of those IDs only) and `03_sql/fetch_sot_subtypes.sql` (SOT sub-types of those listings' SKUs only), in a read-only transaction.
- **Product/Sub-Type** (`map_products.py`): SOT `product_subtype`, else `sub_type` → Mapping Source `SOT_SUBTYPE`. If there is no SOT value, the eBay category leaf → `EBAY_CATEGORY`. If neither exists → `NOT VERIFIED`. The title is never used. As of 2026-09-22 none of the 12 listings' SKUs exist in the SOT, so all 12 use `EBAY_CATEGORY`.
- **Search term**: `"LED " + sub-type`. There is no prefix if it already contains "LED", or if the category is outside `Lighting` (e.g. the waste pipe → "Electrical Wires & Cables").

## 4. Competitor research (`research.py`, Keyword Analysis.pdf steps 1–7)

UK exit check → eBay UK search with `LH_BIN=1` (Buy It Now), `LH_ItemCondition=3` (New), `LH_PrefLoc=1` (UK Only), pages 1–3 → exclude our accounts (seller names Ledsone / Electricalsone / sunsone / LightingSone, every store in `ebay_campaigns.seller_stores`, and any result whose listing ID is ours in the DB) → screen each result against **this listing's own title** (EXACT MATCH / SIMILAR / SAME CATEGORY) → shortlist 6 → open each item page and seller description → final up to 5 (product match, then item-page "N sold", then eBay order; must be located in the UK, not ended, not internal). 3–5 final = `VERIFIED`, 2 = `PARTIAL`, fewer = `NOT_VERIFIED`.

- **Last 30 Days Sales is always NOT VERIFIED.** eBay's purchase-history page requires sign-in behind a CAPTCHA, and CAPTCHAs are never bypassed. If eBay shows a CAPTCHA or sign-in page, research stops for that run and the ID is `NOT_VERIFIED` (retried next run).
- One search capture per search term per day, and one item capture per competitor per day. Each Product ID's evidence file names the captures it used.

## 5. Keywords and Keyword Rank

- `extract_keywords.py`: phrases repeated in **≥2 of that Product ID's own final competitor titles**. Short-tail = 1–2 words, long-tail = 3+ words. Primary = top short-tail with the product head noun; Secondary = next 3 short-tail; Long-Tail = top 3; Competitor = top 3 other repeated phrases **not in our own title**. The requirement CSV's 5 example rows are never used as keywords.
- `calculate_ranks.py`: **Keyword Rank = number of that ID's final competitor listings whose title OR description contains the phrase.** Matching is case-insensitive and whole-word, allows a space or hyphen between words and an optional plural "s/es", and counts each listing once. With no competitors the rank is `NOT VERIFIED`, never 0 and never estimated. It is not a search position or a sales figure.

## 6. Daily flow, failure handling, rerun and resume

```
PREFLIGHT → FETCH (approved IDs) → VALIDATE SOURCE → DETECT CHANGES → MAP → RESEARCH → KEYWORDS → RANKS
→ BUILD (07_report/.staging) → VALIDATE (24 checks) → PASS? ─no→ nothing published, previous dashboards kept
                                                   └yes→ replace 07_report/keyword_check_kobiga.html → PH push → ARCHIVE → summary
```

| Situation | What happens |
|---|---|
| An approved ID not found in the DB | Run stops (`SOURCE_FAILED`); nothing is built or published |
| Validation fails | `VALIDATION_FAILED`; live HTML and PH untouched; the failed page stays in `07_report/.staging/` for inspection |
| Browser / VPN down, CAPTCHA | Affected IDs `FAILED` / `NOT_VERIFIED`; rows show the last verified evidence **with its own date**; retried next run |
| PH push fails | `PUBLISH_FAILED`; local dashboard updated; `05_evidence/research_logs/ph_state.json` keeps it *pending*; the next run retries it |
| Run killed mid-way | Next run resumes: IDs `VERIFIED`/`PARTIAL` today are not researched again; an `IN_PROGRESS` ID is redone |
| Same run twice | No duplicate rows, competitors or keywords (keyed by Product ID / listing ID); PH upsert per user; identical PH content is skipped; one scheduled task |
| Two runs at once | The second exits `ALREADY_RUNNING` (lock `05_evidence/research_logs/run.lock`; a stale lock is cleared) |

**Freshness labels on every row:** `CURRENT` (researched live on this run's date) · `CARRIED FORWARD from <date>` · `NOT VERIFIED` · `LISTING ENDED`.

## 7. Where things are stored

| What | Where |
|---|---|
| DB snapshot per run | `05_evidence/database/<date>/source_snapshot_<run_id>.json` |
| Mapping / search terms | `02_source_mapping/product_mapping/<date>/`, `02_source_mapping/keyword_mapping/<date>/` |
| eBay search pages | `04_research/search_results/<date>/` |
| Competitor item pages / descriptions | `04_research/competitor_listings/<date>/`, `04_research/descriptions/<date>/` |
| Per-ID research + keywords + rank matches | `04_research/keyword_evidence/<date>/<product_id>.json` |
| Imported history (old project, 2026-09-22) | `04_research/*/imported_2026-09-22/` |
| Research status (resume) | `05_evidence/research_logs/research_status.json` |
| Run log / events / summary | `05_evidence/research_logs/<date>/run_<run_id>.log`, `.events.jsonl`, `run_summary_<run_id>.json` |
| Validation results | `06_validation/<date>/local_validation_<run_id>.json` (dry runs: `dry_run_validation_*`, preflight: `preflight_*`) |
| Screenshots | `05_evidence/screenshots/<date>/` |
| PH publish attempts | `05_evidence/database/ph_publish_log.jsonl` |
| Archive per run | `11_archive/YYYY/MM/DD/<run_id>/`: scope, snapshot, mapping, dataset, dashboard, validation, PH result, summary, md5 manifest |

**To answer "what was refreshed for Product ID X on date Y, which competitors, which ranks, what went to PH":** open `11_archive/Y/<run_id>/dataset.json` (row X), `manifest.json` (evidence files + md5), and `ph_publish.json`; the raw pages are at the paths listed in row X's competitors.

## 8. Files

| File | Stage | Reuses |
|---|---|---|
| `config.py` | settings (no secrets) | — |
| `scope.json` | approved IDs | — |
| `logger.py` | logging | — |
| `fetch_data.py` | S2 fetch | `build_population_mapping.py` rules |
| `validate_data.py` | S3 source gate | `validate_requested.py` |
| `detect_changes.py` | S4 | — |
| `map_products.py` | S5 | `build_population_mapping.py` SOT rule |
| `research.py` | S6 | `research_groups.py`, `research_ids.py` |
| `extract_keywords.py` | S7 | `analyze_groups.py` |
| `calculate_ranks.py` | S8 | `analyze_groups.py` |
| `generate_dashboard.py` | S9 | `build_report_requested.py` |
| `validate_dashboard.py` | S10 | `validate_requested.py` |
| `publish.py` | S11–S12 | `publish_ph_task.py` |
| `archive.py` | S13 | `build_evidence.py` |
| `run.py` | orchestrator | — |
| `import_history.py` | one-time history import (done 2026-09-22) | — |
| `scheduler.ps1` | daily task | — |
| `test_automation.py` | tests | — |

Reused code was **copied** from `C:\Users\LED 222\Keywords check\01_Source\` (each file names its source). That old project is not imported, not modified, and not needed at run time.
