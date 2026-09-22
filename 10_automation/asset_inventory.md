# Asset Inventory: Keyword Check – Kobiga Automation

| Field | Value |
|---|---|
| Purpose | Phase 1 of the daily-automation task: record every existing asset, whether it can be reused, and how it will be used. Nothing is built before this is reviewed. |
| Date | 2026-09-22 |
| Status | DRAFT, awaiting review |
| Scope inspected | `C:\Users\LED 222\Keyword_Check_Kobiga\` (new project) and `C:\Users\LED 222\Keywords check\` (old project, read-only) |
| Governing documents | `Mini-AIOS_Master_Instruction_and_Skill_Guide (1).docx` (Skills 04 Existing Asset First, 05 Duplicate Truth, 08 Evidence First, 12 Storage); `Downloads\Common Automation Workflow (1).md`; `00_requirements/Keyword Analysis.pdf`; `00_requirements/System Task - Keyword check- Kobiga.csv` |
| Old project modified? | No. All inspection was read-only. No database queries and no eBay requests were made. |
| Decision order | Reuse → Extend → Merge → Create New |

## 1. New project: current contents

| Asset | Status |
|---|---|
| `README.md` | Project description only |
| `00_requirements/System Task - Keyword check- Kobiga.csv` | Copy of the old `00_Requirements` file; md5 `d03d2b9f…` matches |
| `00_requirements/Keyword Analysis.pdf` | Copy of the old `00_Requirements` file; md5 `3b83feff…` matches |
| All other folders | Empty |

There is no existing automation, scheduler, config, SQL or validator in the new project, so no duplicate-risk exists inside it.

## 2. Requirement and methodology (sources of truth)

| Asset | Purpose | Reusable? | Reason | Proposed use |
|---|---|---|---|---|
| `System Task - Keyword check- Kobiga.csv` | Defines the 11 output columns, the Rank definition ("How many times Competitors Use in the Title Specific or Des…", truncated in source) and the Document URL | YES | This is the canonical output contract | `generate_dashboard.py` and `validate_dashboard.py` read the column list, Rank definition and Document URL **from the CSV at run time**, never retyped. The 5 product rows are examples/templates only, not scope. |
| `Keyword Analysis.pdf` (8 steps) | Research method: UK VPN, "Product Sub-Type + LED", Buy It Now + New + UK Only, pages 1–3, exclude Ledsone/Electricalsone/sunsone, shortlist 6–8, 30-day sales, final 3–5, keyword extraction | YES | This is the canonical method | Step-by-step reference for `research.py` and `extract_keywords.py`. Each rule is cited in the code docstrings. |

## 3. Old project scripts (`Keywords check\01_Source\`, 25 files)

### 3a. Source / population / mapping

| Existing asset | Purpose | Reusable? | Reason | Proposed use |
|---|---|---|---|---|
| `build_population_mapping.py` | Reads the live UK population (`listings.ebay_listings`, filter `site='UK' and status='Active' and is_ended=0 and is_parent=1`), resolves sub-type from SOT (`configurator.components_sot_*`, `product_subtype` then `sub_type`, `[VERIFY` values ignored), falls back to the eBay category leaf, builds the search term (sub-type + "LED" when more than half of our titles contain LED), and exports internal accounts (`ebay_campaigns.seller_stores` + all our item IDs) | YES, extend | Correct read-only SQL; documented SOT and category rules; no hardcoded SKUs | Split it: the SQL goes to `03_sql/*.sql` and `fetch_data.py`; the sub-type rule goes to `map_products.py`. **Change:** the LED-prefix rule is currently decided per *group* (share of our titles); it must be decided per SKU/Product ID. Group IDs are dropped. |
| `population_snapshot.py` | Early sizing snapshot; classifies titles into the 5 CSV product types | NO | Different filter (`coalesce(is_child,0)=0` instead of `is_parent=1`) creates a duplicate-truth risk; the title rule is for sizing only; hardcodes item `267774851327` | Not used. The filter conflict is recorded in Section 7. |
| `run_requested_ids.py` | 12 requested IDs plus listings linked by shared SKU across marketplaces | PARTIAL | The `MAP` dict hardcodes 12 Product IDs and hand-assigned sub-types, which is forbidden by Phase 3/4. The linked-listing SQL (shared SKU, `wrong_sku=0`) is sound. | Only the linked-listing SQL pattern is reusable, and only if cross-marketplace listing becomes a requirement. Not in the daily scope by default. |
| `run_single_id.py` | One-off run for `267256572200` with a manually assigned sub-type | NO | Hardcoded ID and manual mapping | Not used. |

### 3b. eBay research (browser)

| Existing asset | Purpose | Reusable? | Reason | Proposed use |
|---|---|---|---|---|
| `research_groups.py`: `parse_page`, `internal`, `toks`, `has_word`, `goto`, `check_uk`, `Blocked` | Parses search-result cards (listing ID, title, seller, sold, page, position); detects internal accounts; retries navigation; **raises `Blocked` on captcha/sign-in (never bypassed)**; enforces GB exit via ipinfo | YES, reuse | Tested on 190 groups and 33 IDs; correct stop-on-CAPTCHA behaviour | Move into `research.py` as library functions. The CDP URL `http://127.0.0.1:9222` moves to config. The internal-token list keeps `ledsone, led_sone, electricalsone, sunsone, lightingsone` plus DB stores and our item IDs. |
| `research_groups.py`: `research()`, `main()`, `screening_profile()` | Group-level research loop | NO | The 190-group architecture is excluded as the reporting unit by Phase 4 | Not used. |
| `research_ids.py`: `search_capture`, `item_capture`, `profile`, `screen`, `research_id`, `soldn` | **Per Product ID** research: search pages 1–3 → exclude internal → screen against this listing's own title (EXACT / SIMILAR / SAME CATEGORY) → shortlist 6 → item page + description → final 5 (tier, item-page sold, eBay order) → keywords → ranks. Search capture is cached per search term; item capture per listing ID. | YES, extend | Closest existing match to the target SKU-level design; already resumable per ID file; 33/33 VERIFIED in the last run | Core of `research.py`. Required extensions: **(1)** caches currently never expire (`if f.exists(): return`), so a freshness policy with `captured_at` must be added; **(2)** a persistent status (PENDING / IN_PROGRESS / VERIFIED / PARTIAL / NOT_VERIFIED / FAILED) replaces "file exists"; **(3)** extraction and rank are split out into their own stages; **(4)** paths come from config, not the old project. |
| `capture_search.py`, `parse_pool.py`, `shortlist.py`, `capture_items.py` | First-generation pipeline for the 5 CSV example products | NO | `TERMS` hardcodes the 5 products; `shortlist.py` has hand-written per-product rules; `parse_pool.py` reads another project (`Listing_Title_Competitor_Analysis\02_Data\internal_accounts.json`) | Not used. They are superseded by `research_ids.py`. |
| `uk_check.py`, `probe_item.py`, `probe_ph.py` | GB-exit check; probes that proved `/bin/purchaseHistory` redirects to sign-in CAPTCHA | PARTIAL | `uk_check.py` logic is already in `check_uk()`; the probes hardcode IDs | `uk_check` logic is used by `run.py --preflight`. The probe result is the evidence for "Last 30 Days Sales = NOT VERIFIED". |

### 3c. Keyword extraction and rank

| Existing asset | Purpose | Reusable? | Reason | Proposed use |
|---|---|---|---|---|
| `analyze_groups.py`: `clean_description`, `matcher`, `sing`, `ngrams`, `extract`, `choose` | Description boilerplate removal; case-insensitive whole-word phrase matcher (space/hyphen, optional plural s/es on last word); n-gram extraction from final competitor titles (phrase must appear in ≥2 titles; no crossing punctuation; stop-word edges removed; subsumed phrases dropped); Primary / Secondary / Long-Tail selection | YES, reuse | Documented, deterministic, matches PDF Step 8 and the Short-tail (1–2 words) / Long-tail (3+) definitions | `extract_keywords.py` (extract, choose, competitor-keyword rule "not in our own title") and `calculate_ranks.py` (matcher + clean_description). |
| `analyze_groups.py`: `main()` | Group dataset build | NO | Group architecture | Not used. |
| `compute_rank.py` | Ranks the CSV's 40 example keywords over 5 competitors | NO | Tied to the 5 example rows and `shortlist.json` | Not used. It proves the Rank definition: count of final competitors whose title OR description matches. |
| `provisional_lampshade_check.py` | Title-only check against another project's data | NO | Provisional; reads an external project; titles only | Not used. |

### 3d. Dashboard, evidence, validation, publish

| Existing asset | Purpose | Reusable? | Reason | Proposed use |
|---|---|---|---|---|
| `build_report_requested.py` | Latest standalone HTML: 11 requirement columns under a "Keyword" group header, one Rank per keyword, hover evidence, search box + filters, competitor and keyword-evidence tables, inline CSS/JS, dark mode | YES, extend | Layout and standalone contract are proven | Base for `generate_dashboard.py`. **Change:** rows come from the latest snapshot's SKU-level results (all eligible SKUs, not 12 IDs); add freshness columns (`source_updated_at`, `research_captured_at`, `last_successful_refresh`, `verification_status`); add a filter for status and freshness. At ~8,500 rows the data should be embedded as JSON and rendered by JS rather than as pre-built `<tr>` HTML. |
| `build_report.py`, `build_report_id.py` | Earlier report builders (5 examples; 1 ID) | NO | Superseded by `build_report_requested.py` | Not used. |
| `validate_requested.py` | Independent validation: column order from CSV; DB re-derivation of rows; **rank recount with a different matcher (token sequence) from raw item HTML + descriptions**; traceability to captured search pages; GB exit + filter params in URLs; no internal sellers; UK location; 3–5 competitors on VERIFIED; standalone (no external script/css/img); headless Chrome load with zero JS errors and zero network requests; filter test | YES, extend | Independent recount is strong evidence practice | Base for `validate_dashboard.py`, plus research and keyword gates in `validate_data.py`. Remove the hardcoded `REQ` list; the expected population comes from the day's snapshot. |
| `validate_html.py`, `validate_id.py` | Validators for older report versions | PARTIAL | Hardcoded 5 rows / 1 ID | Reuse only the `HTMLParser` table reader from `validate_html.py` if needed. |
| `build_evidence.py`, `build_evidence_id.py` | Competitor evidence CSV, keyword-rank workings CSV, md5 manifest | YES, extend | The CSV column sets match Phase 6 capture fields; the manifest gives integrity | `archive.py` writes the same CSVs per day plus the md5 manifest. |
| `publish_ph_task.py` | Upserts the HTML into `tech_team_outputs.ph_task` for 8 users (transactional, idempotent, md5-verified) | NO by default (RED/AMBER) | This is a **write to a production database** and is outside this task's approved scope (Guide 0.1 §7 RED: production data changes, live automation) | `publish.py` does an **atomic local file replace** only. DB publish is a separate, approval-gated step (Section 7, Q4). |

## 4. Old project data and evidence (`Keywords check\02_Data`, `04_Evidence`, `05_Validation`)

| Existing asset | What it holds | Reusable? | Reason | Proposed use |
|---|---|---|---|---|
| `02_Data/population/listings.json`, `population_summary.json`, `uk_active_ebay_listings.csv` | Population snapshot from 2026-09-22 05:25 UTC: 8,502 eligible listings, 4,883 distinct SKUs, 25,133 SKUs incl. variations; mapping 868 SUB-TYPE and 7,634 CATEGORY-LEVEL; 190 groups | NO as current data | Stale by design; the daily run must query live | May be imported **once** as a labelled historical baseline (`captured_at` kept) so that the first run's change detection has something to compare with. Only with approval (Q3). |
| `02_Data/search_cache/` (8 terms), `item_cache/` (123 listings, all status OK) | Cached search captures and competitor item pages, with `captured_at` | CONDITIONAL | Verified evidence, but captured 2026-09-22 | Could seed the evidence store with the original `captured_at` so the freshness policy decides when to refresh. Never presented as newly researched. Needs approval (Q3). |
| `02_Data/requested/ids/` (33 records, all VERIFIED), `ids_prev/` (48), `ids/267256572200.json`, `04_research/G001–G002` | Per-ID and per-group research results | CONDITIONAL | Same as above; group records do not fit the SKU model | Only the 33 per-ID records could seed. Group records are not used. |
| `02_Data/keyword_check_dataset.json`, `groups.json`, `keyword_rank.json`, `candidate_pool*.json`, `shortlist.json`, `search_capture.json`, `item_capture.json` | Outputs of the superseded group and example pipelines | NO | Group architecture or the 5 example rows | Not used. |
| `04_Evidence/` (raw search HTML, 246 item/desc raw files, evidence CSVs, run logs, `EXECUTION_EVIDENCE.md`, `manifest.json`) | Raw proof for the earlier runs | Reference only | Historical proof for the old report | Not copied (to avoid duplicate raw files, Phase 12). Referenced by path if the seed option is approved. |
| `03_Report/keyword_check_kobiga.html` | Last published old report (12 requested IDs; validation `overall: PASS`, 12 rows) | NO | Different scope (12 IDs, not the full population) | Not reused as the production dashboard. The new dashboard is generated only by the pipeline. |
| `05_Validation/html_validation_result.json`, screenshots | Last validation result | Reference only | — | The pattern (JSON checks list + overall PASS/FAIL + screenshot) is kept for `06_validation/`. |

## 5. Environment and dependencies (checked, not changed)

| Item | Finding | Use |
|---|---|---|
| Python | 3.13 (`C:\Program Files\Python313`) | Runtime |
| Libraries | `psycopg`, `playwright`, `bs4` import OK; `pypdf` available | Existing stack, no new dependencies needed |
| DB connection | Env var `WLP_SOURCE_DB_URL` is set (value not read or printed). Scripts open read-only transactions. | `config.py` reads the same variable. No credential is stored in files. |
| Publish DB vars | `publish_ph_task.py` expects `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` | Not used unless Q4 is approved |
| Browser | UK-VPN Chrome reached over CDP `127.0.0.1:9222`; own tab only; GB exit checked via `ipinfo.io` | `config.py`: `KWC_CDP_URL`, `KWC_REQUIRED_COUNTRY=GB` |
| Git | Neither project is a git repository | Guide Skill 12 expects a GitHub path. Flagged, not blocking. |

## 6. Hardcoded values found in the old code (must not be carried forward)

| Location | Hardcoded value | Replacement |
|---|---|---|
| `capture_search.py` `TERMS` | 5 product names → search terms | Per-SKU term from `map_products.py` |
| `run_requested_ids.py` `MAP`, `validate_requested.py` `REQ` | 12 Product IDs + manual sub-types | DB population |
| `run_single_id.py`, `build_report_id.py`, `validate_id.py`, `build_evidence_id.py` | `267256572200` | DB population |
| `population_snapshot.py`, `shortlist.py`, `probe_item.py` | `267774851327` | Removed |
| `parse_pool.py`, `provisional_lampshade_check.py` | Path into `Listing_Title_Competitor_Analysis` | Internal accounts from the DB (`ebay_campaigns.seller_stores` + own item IDs) |
| All browser scripts | `http://127.0.0.1:9222` | `KWC_CDP_URL` |
| `research_ids.py` | `SHORTLIST, FINAL = 6, 5` | Config (`KWC_SHORTLIST=6`, `KWC_FINAL_MAX=5`, `KWC_FINAL_MIN=3`) |
| `publish_ph_task.py` | 8 user names, developer name | Out of scope unless Q4 |

## 7. Risks and open questions (need a decision before Phase 2)

> **Scope update (user, 2026-09-22):** scope is only the approved Product IDs held in `10_automation/scope.json`, not the full population. Q1 is withdrawn (no volume problem at 12 IDs). Q2 is answered (SOT → eBay category fallback approved; no title inference). Q4 is answered (PH publish approved after local validation). Q6: one row per approved Product ID. Q3 and Q5 carry over. The current open decisions are in `WORKFLOW_DESIGN.md` §11.

| # | Issue | Evidence | Risk | Recommendation |
|---|---|---|---|---|
| Q1 | **Research volume vs. "daily".** About 8,500 eligible listings. Each new ID needs up to 3 search pages plus 6 item pages; searches are shared per search term. | `population_summary.json`; `research_ids.py` | A full first run is days of browser time with CAPTCHA risk; a daily full rescrape is not feasible | Phase 5 change detection plus a freshness policy, e.g. search captures valid **7 days**, competitor item pages valid **14 days**, and a daily research budget (`KWC_MAX_RESEARCH_PER_RUN`). Rows past freshness show their last capture date and a STALE status. **Please confirm the freshness windows and daily budget.** |
| Q2 | **Mapping quality.** 7,634 of 8,502 listings (90%) have no SOT sub-type and fall back to the eBay category leaf (e.g. "Ceiling Lights & Chandeliers"), which the old project itself judged too broad for a search term. | `population_summary.json`; `run_single_id.py` docstring | Broad search terms give weak competitors. Inventing a sub-type from titles would break "no invented mappings". | Keep SOT → category leaf, and label CATEGORY-LEVEL rows clearly as such. Do not derive sub-types from titles unless you approve a documented rule. **Please confirm.** |
| Q3 | **Seeding from the old project.** 33 VERIFIED ID records and 123 item captures exist from 2026-09-22. | `02_Data/requested/ids`, `item_cache` | Copying them duplicates raw files; ignoring them wastes verified work | Option A: start clean (first run = baseline). Option B: import them once as history with their original `captured_at`, read-only from the old path. **Please choose.** |
| Q4 | **PUBLISH meaning.** The old project also published to `tech_team_outputs.ph_task` (production DB write). | `publish_ph_task.py` | RED work without written approval | Default: PUBLISH = atomic replace of `07_report/keyword_check_kobiga.html` only. DB publishing only on your explicit approval. |
| Q5 | **Population filter conflict.** `is_parent=1` (used by the mapping and research pipeline) vs `coalesce(is_child,0)=0` (sizing script). | `build_population_mapping.py`, `population_snapshot.py` | Two definitions of "eligible" | Use `site='UK' and status='Active' and is_ended=0 and is_parent=1`, as the last validated pipeline did. Record it once in `03_sql/` as the canonical rule. |
| Q6 | **SKU vs Product ID grain.** 8,502 listings but 4,883 distinct parent SKUs, so one SKU can be on several listings. | `population_summary.json` | The dashboard's row unit must be fixed | Row = one Product ID (listing) with its SKU, as the requirement's sample row and last validated report did. Change detection keys on Product ID and tracks SKU changes as a CHANGED attribute. |
| Q7 | **Last 30 Days Sales** cannot be read without passing an eBay sign-in CAPTCHA | `04_Evidence/ebay_raw/probe_ph_266472322515.txt` | — | Always `NOT VERIFIED`. The final selection uses item-page "N sold" (lifetime) as the verified sales signal, as before. |
| Q8 | **CSV columns vs PDF Expected Result.** The PDF also lists Short-Tail Keywords and Keyword Opportunities, which have no CSV column. | CSV row 3; PDF Step 8 | Adding columns would be invented scope | Keep the 11 CSV columns only. |
| Q9 | **Runtime needs a live UK-VPN Chrome.** Research cannot run unattended if Chrome/VPN are down at the scheduled time. | All browser scripts | The scheduled run would fail | The scheduler runs anyway: DB refresh, change detection, dashboard rebuild and validation still complete. Research stages record NOT_VERIFIED / PENDING and resume next run. Preflight reports VPN/CDP state. |

## 8. Reuse summary

| Decision | Assets |
|---|---|
| **Reuse** (move into the new automation with config-driven paths) | `research_groups.py` helpers (`parse_page`, `internal`, `goto`, `check_uk`, `Blocked`, `toks`, `has_word`); `analyze_groups.py` (`clean_description`, `matcher`, `ngrams`, `extract`, `choose`) |
| **Extend** | `build_population_mapping.py` → `fetch_data.py` + `map_products.py` (per-SKU LED rule, no groups); `research_ids.py` → `research.py` (freshness, status, resume); `build_report_requested.py` → `generate_dashboard.py` (full population, freshness, JSON-embedded rows); `validate_requested.py` → `validate_dashboard.py` + `validate_data.py`; `build_evidence.py` → `archive.py` |
| **Create new** (no existing asset) | `config.py`, `logger.py`, `detect_changes.py`, `calculate_ranks.py` (split from `research_id`), `publish.py` (atomic local replace), `run.py` (stage orchestrator, `--dry-run/--as-of/--preflight`), `scheduler.ps1`, `test_automation.py`, `10_automation/README.md`, `08_handover/HANDOVER.md` |
| **Not used** | `population_snapshot.py`, `run_single_id.py`, `run_requested_ids.py` (except the linked-SKU SQL pattern), `capture_search.py`, `parse_pool.py`, `shortlist.py`, `capture_items.py`, `compute_rank.py`, `build_report.py`, `build_report_id.py`, `validate_html.py`, `validate_id.py`, `build_evidence_id.py`, `provisional_lampshade_check.py`, `probe_*.py`, `publish_ph_task.py` (unless Q4) |

**Copying approach:** reused functions are copied into `10_automation/` with a header naming their source file in the old project. The new project must not import from the old folder, so that the old project stays unmodified and the new one is self-contained.

## 9. Pass / fail for Phase 1

- **PASS** if every old script and data folder is listed with a reuse decision, hardcoded values are identified, and open decisions are raised before any build.
- **Result:** 25/25 scripts and all data/evidence folders are classified; 8 hardcoded-value locations are listed; 9 open questions are raised.
- **Next step:** review Q1–Q6, then start Phase 2 (workflow design).
