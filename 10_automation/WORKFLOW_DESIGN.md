# Daily Automation Workflow Design: Keyword Check – Kobiga

| Field | Value |
|---|---|
| Purpose | Phase 2 design of the daily automation, for review before any code is written |
| Date | 2026-09-22 |
| Status | APPROVED and IMPLEMENTED 2026-09-22 (decisions in §11; how to run: `README.md`) |
| Supersedes | Scope assumptions in `asset_inventory.md` §7 Q1, Q2, Q4, Q6 (full-population scope withdrawn) |
| Inputs | `asset_inventory.md`; Scope Confirmation (user, 2026-09-22); `00_requirements/Keyword Analysis.pdf`; `00_requirements/System Task - Keyword check- Kobiga.csv`; Mini-AIOS guide; Common Automation Workflow guide |
| Not done in this phase | No code, no DB query, no eBay request, no scheduler, no PH write |

---

## 1. Confirmed scope

| Rule | Design consequence |
|---|---|
| Scope = the approved Product IDs only (12) | Stored once in `10_automation/scope.json`, the single source of truth. Every SQL query filters `item_id = any(%(ids)s)`. No query anywhere selects the whole UK population. |
| Scope changes only by editing the config | `scope.json` carries `version`, `approved_by`, `approved_at`, `change_note`. Each run copies it into its archive. A change in the ID list between runs is logged as `SCOPE_CHANGED`, never inferred. |
| No 190-group architecture, no example keywords reused | Research, keywords and ranks are computed per Product ID from that ID's own competitors. CSV example keywords are never read as data; only the CSV's column headers, Rank definition and Document URL are read. |
| Sub-type: SOT → eBay category fallback → NOT VERIFIED; no title inference | See §5 stage MAP |
| Local validation gates the PH push | See §6 and §7 |

### Approved Product IDs (final, `scope.json` v2)

```
265660310933  267742103780  267791295531  267784997642  267773888902  267768578649
267765767284  267761469770  267728257222  267720120199  267695260771  267687534749
```

> **Resolved (D1): `267765767284` approved, `267765726284` rejected.** Original note: `267765726284` does not match any record in the old project. The old project researched **`267765767284`** in its place ("Vintage E27 Wall Sconce Light Glass Shade Antique Brass Indoor Lamp Fixture", Electricalsone). The middle digits are transposed (`…7672…` vs `…7267…`). The other 11 IDs match exactly. The config will hold the ID **as you supplied it**. The Phase 3 preflight will stop if an ID does not resolve in the DB. Please confirm which ID is correct.

---

## 2. Flow

```
scheduler.ps1 (daily, Windows Task Scheduler)
      │
      ▼
run.py ── lock (one run at a time) ── run_id ── load config + scope.json
      │
 S1 PREFLIGHT ─────────────── config valid · DB reachable · CDP/VPN state · PH creds present
      │
 S2 FETCH ─────────────────── live DB, approved IDs only → source snapshot
      │
 S3 VALIDATE SOURCE ───────── every ID resolved, fields present, no duplicates  ──FAIL──► STOP (no build, no publish)
      │
 S4 DETECT CHANGES ────────── vs last successful snapshot: NEW / CHANGED / UNCHANGED / REMOVED
      │
 S5 MAP ───────────────────── SOT sub-type → eBay category → NOT VERIFIED; search term
      │
 S6 RESEARCH (resumable) ──── per ID: eBay UK search p1-3 → exclude internal → screen → shortlist 6 → item pages → final 3-5
      │                        blocked/VPN down → ID = NOT_VERIFIED/FAILED, progress saved, continue with next safe step
 S7 EXTRACT KEYWORDS ──────── per ID, own final competitor titles only
      │
 S8 CALCULATE RANKS ───────── per keyword, count of final competitors whose title OR description contains it
      │
 S9 BUILD DASHBOARD ───────── 07_report/.staging/<run_id>.html (never the live file)
      │
 S10 VALIDATE OUTPUT ──────── scope · data · competitor · rank recount · HTML/browser
      │
      ├── FAIL ─► keep 07_report/keyword_check_kobiga.html + PH unchanged · log failure · status VALIDATION_FAILED
      │
      ▼ PASS
 S11 PUBLISH LOCAL ────────── atomic replace of 07_report/keyword_check_kobiga.html
      │
 S12 PUBLISH PH ───────────── upsert KWC rows in tech_team_outputs.ph_task, verify md5 from a fresh connection
      │
      ├── FAIL ─► local validated HTML stays · status PUBLISH_FAILED · next run retries the PH push
      │
      ▼ PASS
 S13 ARCHIVE ──────────────── 11_archive/YYYY/MM/DD/ run package + manifest (md5 of every evidence file)
      │
 S14 LOG / STATUS ─────────── run_summary.json · run.log · final status
```

This maps onto the Common Automation Workflow as follows: Scheduler → Configuration (S1) → Fetch (S2) → Validate Source (S3) → Business Logic (S4–S8) → Generate Output (S9) → Validate Output (S10) → Publish (S11–S12) → Archive (S13) → Logging (S14).

---

## 3. Files (`10_automation/`)

| File | Stage | Reuses (copied, source cited in header) | New work |
|---|---|---|---|
| `scope.json` | — | — | Approved ID list, the single source of truth |
| `config.py` | S1 | — | Paths, env-var names, limits, freshness, PH settings; no secrets |
| `logger.py` | all | — | Run log (text + JSON lines), per-stage timing |
| `fetch_data.py` | S2 | SQL from `build_population_mapping.py`, `run_requested_ids.py` | ID-filtered queries; snapshot writer |
| `validate_data.py` | S3, S6, S8 gates | Checks from `validate_requested.py` | Source gate and research gate |
| `detect_changes.py` | S4 | — | Snapshot diff |
| `map_products.py` | S5 | SOT rule from `build_population_mapping.py` | Per-ID mapping; search-term rule (§5, D2) |
| `research.py` | S6 | `research_groups.py` (`parse_page`, `internal`, `goto`, `check_uk`, `Blocked`, `toks`, `has_word`); `research_ids.py` (`search_capture`, `item_capture`, `profile`, `screen`, final selection) | Status store, resume, freshness, dated evidence paths |
| `extract_keywords.py` | S7 | `analyze_groups.py` (`ngrams`, `extract`, `choose`, `sing`); competitor-keyword rule from `research_ids.py` | Split into its own stage |
| `calculate_ranks.py` | S8 | `analyze_groups.py` (`matcher`, `clean_description`) | Split into its own stage; rank workings output |
| `generate_dashboard.py` | S9 | Layout/CSS/JS from `build_report_requested.py` | Freshness/status columns; data from the run dataset; staging output |
| `validate_dashboard.py` | S10 | `validate_requested.py` (independent token recount, standalone + headless Chrome checks) | Scope from `scope.json`; freshness checks |
| `publish.py` | S11, S12 | `publish_ph_task.py` (transactional upsert on `(project_code, assigned_user)`, KWC-scoped row guard, fresh-connection md5 verify) | Atomic local replace; "unchanged → skip"; retry state |
| `archive.py` | S13 | Manifest/CSV pattern from `build_evidence.py` | Dated run package |
| `run.py` | orchestrator | — | Stage runner, `--dry-run / --preflight / --as-of / --stage / --resume` |
| `scheduler.ps1` | trigger | — | Registers/updates one scheduled task (idempotent) |
| `test_automation.py` | tests | — | Unit + fixture tests (§10) |
| `README.md` | docs | — | Unknown-developer guide |

SQL goes in `03_sql/` as named files (`fetch_listings.sql`, `fetch_skus.sql`, `fetch_sot_subtypes.sql`, `fetch_internal_accounts.sql`). Each takes the ID list as a parameter; none embeds IDs.

---

## 4. Data layout (uses the folders already created)

| Path | Written by | Content | Overwrite? |
|---|---|---|---|
| `05_evidence/database/YYYY-MM-DD/source_snapshot.json` (+ `.csv`) | S2 | Per ID: run_id, run_date, as_of, Product ID, SKU, variation SKUs, title, marketplace, account, listing status, is_ended, eBay category path, category_id, `source_updated_at` (DB `updated_at` if the column exists; otherwise `NOT AVAILABLE`, never invented), fetch status | Never; a same-day rerun writes `…_r2` and the run summary names the one used |
| `02_source_mapping/product_mapping/YYYY-MM-DD/mapping.csv` | S5 | Product ID, SOT sub-type, eBay category, Product/Sub-Type used, Mapping Source (`SOT_SUBTYPE`/`EBAY_CATEGORY`), Mapping Status, note | Same rule |
| `02_source_mapping/keyword_mapping/YYYY-MM-DD/search_terms.csv` | S5 | Product ID, source value, rule applied, Search Term | Same rule |
| `04_research/search_results/YYYY-MM-DD/<term_key>_p{1,2,3}.html` + `<term_key>.json` | S6 | Raw result pages + parsed cards (listing ID, card title, seller, sold, page, position, internal flag), URL with filters, HTTP status, exit IP, `captured_at` | Written once per term per day; IDs with the same term share it (recorded explicitly) |
| `04_research/competitor_listings/YYYY-MM-DD/item_<listing_id>.html` + `.json` | S6 | Item page + parsed title, seller, sold, location, ended flag, `captured_at` | Once per listing per day |
| `04_research/descriptions/YYYY-MM-DD/desc_<listing_id>.txt` | S6 | Seller description text | Once per listing per day |
| `04_research/keyword_evidence/YYYY-MM-DD/<product_id>.json` | S6–S8 | Per ID: screening profile, candidates, shortlist, final competitors (with evidence paths), keywords, rank matches + snippets | Upsert per ID |
| `05_evidence/research_logs/research_status.json` | S6 | **Persistent** per-ID state (§8) | Updated in place, atomically (write temp, then replace) |
| `05_evidence/research_logs/YYYY-MM-DD/run_<run_id>.log` | S14 | Human-readable run log | New file per run |
| `05_evidence/screenshots/YYYY-MM-DD/` | S10 | Headless Chrome screenshots of the staged dashboard | Per run |
| `06_validation/YYYY-MM-DD/local_validation_<run_id>.json` | S3, S10 | Every check: name, PASS/FAIL, detail; overall | Per run |
| `07_report/.staging/keyword_check_kobiga.<run_id>.html` | S9 | Built dashboard awaiting validation | Deleted after publish or kept on failure for inspection |
| `07_report/keyword_check_kobiga.html` | S11 | **Live local dashboard** = last validated build | Replaced only after PASS |
| `05_evidence/database/ph_publish_log.jsonl` | S12 | One line per attempt: run_id, timestamp, Product IDs, html md5, rows touched, result, error | Append-only |
| `11_archive/YYYY/MM/DD/<run_id>/` | S13 | `scope.json` copy, `run_summary.json`, `dataset.json` (the exact data embedded in the HTML), `dashboard.html` copy, validation result, PH publish result, `manifest.json` (path + md5 of every evidence file used; raw files are **referenced, not copied**) | Never |
| `09_closure/` , `08_handover/` | Phase 10 | `HANDOVER.md` and the closure note | — |

`--as-of YYYY-MM-DD` sets the run date used for folder names, change comparison and freshness labels. The DB is still read live; it cannot return historical data, and the snapshot records both `as_of` and the real `fetched_at`.

---

## 5. Stage specifications

| # | Stage | Input | Output | Validation rule | Failure condition → action |
|---|---|---|---|---|---|
| S1 | PREFLIGHT | `config.py`, `scope.json`, env vars | `preflight` block in run summary | Config parses; scope has ≥1 ID, all 11–13 digits, no duplicates; `WLP_SOURCE_DB_URL` set; read-only DB connect OK; required tables readable; CDP reachable **and** exit country GB (warning only); PH env vars set and `ph_task` readable (warning only); output folders writable | Config, scope or DB failure → **STOP**, status `PREFLIGHT_FAILED`. CDP/VPN down → continue, research marked `NOT_VERIFIED (browser unavailable)`. PH unreachable → continue, S12 records failure. |
| S2 | FETCH | Scope IDs | `source_snapshot.json` | Read-only transaction; queries filtered by the ID list | DB error after 3 retries → STOP, `SOURCE_FAILED` |
| S3 | VALIDATE SOURCE | Snapshot | Checks → validation file | Every configured ID returns exactly one parent row (`is_parent=1`); SKU, title, site, sub_source not null; no duplicate IDs; site/status/is_ended recorded | A **configured ID not found** → STOP, `SOURCE_FAILED` (we never publish a dashboard with a silently missing ID). A null field → that ID `NOT VERIFIED`, run continues. |
| S4 | DETECT CHANGES | Today's snapshot + last successful snapshot | Per-ID class in the run summary | NEW = not in previous; REMOVED = in previous scope but not in `scope.json`; CHANGED = SKU, title, category, sub-type, status or is_ended differs (the fields that changed are listed); else UNCHANGED | No previous snapshot → all NEW (first run) |
| S5 | MAP | Snapshot + SOT rows for those SKUs | `mapping.csv`, `search_terms.csv` | Sub-type = SOT `product_subtype`, else SOT `sub_type` (`[VERIFY` values ignored), over the listing's SKUs (parent + variation, `wrong_sku=0`), most common wins → `SOT_SUBTYPE`. Else eBay category **leaf** (last segment of `product_type`) → `EBAY_CATEGORY`. Else `NOT VERIFIED`. Search term: see D2. | Mapping `NOT VERIFIED` → no research for that ID; row shown with status |
| S6 | RESEARCH | Mapping, internal-accounts list (DB: `ebay_campaigns.seller_stores` + our item IDs + tokens `ledsone, led_sone, electricalsone, sunsone, lightingsone`) | Raw evidence + `keyword_evidence/<pid>.json` + status | GB exit checked at start and every N IDs; URL filters `LH_BIN=1&LH_ItemCondition=3&LH_PrefLoc=1`; pages 1–3; own tab only; internal excluded by card seller **and** item-page seller; shortlist 6 (PDF: 6–8); eligible = item page served, "Located in" UK, not ended, not internal; final up to 5 by tier → item-page sold → eBay order; VERIFIED ≥3, PARTIAL 2, NOT_VERIFIED <2 | CAPTCHA/sign-in → `Blocked`: never bypassed; the current ID is `NOT_VERIFIED (blocked)` and research stops for this run; other stages continue. Network/VPN error → ID `FAILED`, retried next run. |
| S7 | EXTRACT KEYWORDS | Final competitor titles (that ID only) | Keyword lists per ID | Phrase in ≥2 final titles; short-tail 1–2 words, long-tail 3+; Primary = top short-tail containing the head noun; Secondary = next 3 short-tail; Long-Tail = top 3; Competitor = top 3 remaining phrases **not in our own title** | <2 final competitors → keywords `NOT VERIFIED` |
| S8 | CALCULATE RANKS | Keywords + final competitor titles + cleaned descriptions | Rank per keyword + matches (listing, field, snippet) | Rank = number of final competitors whose title OR description contains the phrase (case-insensitive, whole words, space/hyphen, optional plural on last word); counted once per listing | No competitors → `NOT VERIFIED` (never 0, never estimated) |
| S9 | BUILD DASHBOARD | Run dataset (§6) | Staged HTML + `dataset.json` | Data embedded as JSON; inline CSS/JS; no external URLs except outbound links to eBay/Document | Build exception → `BUILD_FAILED`; live file untouched |
| S10 | VALIDATE OUTPUT | Staged HTML, snapshot, `scope.json`, raw evidence | `local_validation_<run_id>.json` | §7 | Any **critical** FAIL → `VALIDATION_FAILED`; live HTML and PH untouched |
| S11 | PUBLISH LOCAL | Validated staged HTML | `07_report/keyword_check_kobiga.html` | `os.replace` (atomic on the same volume); md5 re-read = staged md5 | Replace error → `PUBLISH_LOCAL_FAILED`; old file still intact |
| S12 | PUBLISH PH | Live local HTML (validated) | PH rows + publish log | See §9 | Failure → `PUBLISH_FAILED`, retried next run |
| S13 | ARCHIVE | All run outputs | `11_archive/YYYY/MM/DD/<run_id>/` | Manifest md5 of every referenced file | Archive error → logged; status carries a warning |
| S14 | LOG / STATUS | Stage results | `run_summary.json`, log | — | — |

### Run statuses

| Status | Meaning |
|---|---|
| `SUCCESS` | Local validation PASS, PH publish PASS (or unchanged hash → skip), every ID researched today |
| `SUCCESS_WITH_CARRIED_FORWARD` | As SUCCESS, but ≥1 ID shows previous verified evidence because today's research failed. The affected IDs are listed. |
| `PUBLISH_FAILED` | Local dashboard validated and published; PH push failed and will be retried |
| `VALIDATION_FAILED` | Nothing published; previous local and PH dashboards unchanged |
| `SOURCE_FAILED` / `PREFLIGHT_FAILED` / `BUILD_FAILED` | Stopped before publish; previous dashboards unchanged |
| `DRY_RUN_OK` / `DRY_RUN_FAILED` | Dry run result |

---

## 6. Dashboard rows and freshness

- **One row per approved Product ID**, in `scope.json` order. The main table has the requirement's 11 columns in CSV order (read from the CSV at build time): SKU · Product ID · Product Name · Primary Keyword · Keyword Rank · Secondary Keywords · Keyword Rank · Long-Tail Keywords · Keyword Rank · Competitor Keywords · Keyword Rank.
- **Per-row sub-line** (not extra requirement columns): marketplace · account · listing status · sub-type · Mapping Source · search term · verification status · **freshness**.
- **Freshness fields** stored per ID: `source_updated_at`, `research_captured_at`, `last_successful_refresh`, `verification_status`, `freshness_label`.

  | Label | Meaning |
  |---|---|
  | `CURRENT` | Researched in today's run |
  | `CARRIED FORWARD from YYYY-MM-DD` | Today's research failed; the previous VERIFIED evidence is shown with its own capture date |
  | `NOT VERIFIED` | No verified evidence exists |
  | `LISTING ENDED` | The DB shows the listing ended or inactive; the row remains, because it is in scope, and the last evidence is labelled with its date |

- Filters: text search (SKU, ID, name, keyword), verification status, freshness, marketplace/account.
- Evidence sections: competitor evidence table (all Phase 4 capture fields) and keyword-rank evidence (keyword → listings → field → snippet). Last 30 Days Sales is always `NOT VERIFIED` (eBay sign-in CAPTCHA, not bypassed).
- A "Run" block shows run_id, run date, DB fetched_at, scope version, and counts by status.

---

## 7. Local validation gate (S10)

All checks are written to `06_validation/YYYY-MM-DD/local_validation_<run_id>.json`. **C** = critical: a FAIL blocks every publish. **W** = warning: recorded, does not block.

| Area | Check | Level |
|---|---|---|
| Scope | Dashboard Product IDs == `scope.json` IDs exactly (none missing, none extra, no duplicates) | C |
| Data | SKU, Product Name, marketplace, account equal a **fresh** read-only DB query (not the snapshot file) | C |
| Data | Every row has Mapping Source and Mapping Status | C |
| Data | Every row has a freshness label; no row labelled `CURRENT` unless its `research_captured_at` date = run date | C |
| Competitor | Every competitor appears in **that ID's** captured search pages (`data-listingid`) | C |
| Competitor | No internal account (tokens + DB store names + our item IDs) | C |
| Competitor | Every search URL has the 3 filters, 3 pages served, GB exit recorded | C |
| Competitor | Every item location contains "United Kingdom" | C |
| Competitor | VERIFIED rows have 3–5 final competitors; PARTIAL has 2 | C |
| Rank | Every numeric rank equals an **independent** recount (token-sequence matcher, different code from the builder's regex) over the raw item-page title + cleaned raw description | C |
| Rank | Every keyword occurs in ≥2 of that ID's final competitor titles; Competitor Keywords are not in our own title | C |
| Rank | No numeric rank shown where competitors < 2 | C |
| HTML | Column headers == CSV columns, in order; "Keyword" group header spans 8 | C |
| HTML | No `<script src>`, stylesheet `<link>`, `@import`, remote `url()`, `<img src=http>`, `<iframe>` | C |
| HTML | Headless Chrome from `file://`: 0 JS errors, 0 network requests, rendered rows = scope count | C |
| HTML | Search box and each filter change the visible row count as expected | C |
| HTML | Rank definition and Document URL from the CSV are present | W |
| Freshness | ≥1 row CARRIED FORWARD or NOT VERIFIED | W (sets run status) |

Research-stage gate (S6, in `validate_data.py`): exit country GB before any capture; evidence files exist for every final competitor. A failure here marks **that ID** `NOT_VERIFIED`; it does not stop the run.

---

## 8. Research status, resume, idempotency

**Persistent per-ID state** in `05_evidence/research_logs/research_status.json`:

```json
{"267742103780": {"status": "VERIFIED", "run_date": "2026-09-23", "run_id": "...", "attempts": 1,
                  "research_captured_at": "...", "last_verified_run_date": "2026-09-23",
                  "last_verified_evidence": "04_research/keyword_evidence/2026-09-23/267742103780.json",
                  "error": null}}
```

Statuses: `PENDING → IN_PROGRESS → VERIFIED | PARTIAL | NOT_VERIFIED | FAILED`.

| Situation | Behaviour |
|---|---|
| New day | Every in-scope ID with mapping is set `PENDING` for today, so all 12 IDs are researched once per day (about 12 × (3 search pages shared per term + 6 item pages); estimated 10–20 min) |
| Same-day rerun | IDs already `VERIFIED`/`PARTIAL`/`NOT_VERIFIED (no competitors)` for today are **skipped**; their evidence is reused; nothing is duplicated |
| Process killed mid-ID | That ID is still `IN_PROGRESS` → treated as incomplete and redone. Completed IDs are untouched. |
| `FAILED` / `NOT_VERIFIED (blocked)` today | Retried on the next run (same day manual or next scheduled run); `attempts` increments |
| Search term shared by several IDs | One capture per term per day; each ID record names the capture file it used |
| Competitor listing shared by IDs | One item capture per listing per day; reused by path |
| Keys | Evidence file names = `run_date` + term key / listing ID / Product ID (deterministic), so a rerun overwrites the same day's file with identical content or skips it. Dashboard rows are keyed by Product ID. Competitor rows by (Product ID, listing ID). |
| Concurrency | `run.py` takes a lock file (`05_evidence/research_logs/run.lock` with PID + start time). A second run exits `ALREADY_RUNNING`. A stale lock (PID not alive) is cleared and logged. |
| PH | Upsert keyed on `(project_code, assigned_user)`, so records are never duplicated. If the published md5 equals the live HTML md5, `PUBLISH_SKIPPED_UNCHANGED`. |
| Scheduler | `Register-ScheduledTask … -Force` with a fixed task name updates the task in place; running the script twice leaves one task |

---

## 9. PH Dashboard publish (S12)

Reuses the tested pattern of `publish_ph_task.py`:

- **Target:** `tech_team_outputs.ph_task`, rows where `project_code = 'KWC'` only. Upsert on `(project_code, assigned_user)`, in one transaction for all audience rows (all or none). A row-count guard is scoped to `KWC`: if the count after the upsert ≠ expected, roll back. The step touches no other project's rows. After commit it re-reads from a **fresh connection** and compares `md5(html_content)` with the local file.
- **Content:** the validated live `07_report/keyword_check_kobiga.html` (never the staging file, never data straight from the DB); `description` generated from the run dataset (IDs, verified counts).
- **Preconditions:** local validation PASS for **this** HTML md5 (the validation file records the md5 it validated). If the md5 differs, publish refuses.
- **Record:** timestamp, run_id, Product IDs, html md5, version, rows updated/inserted, result, error → `05_evidence/database/ph_publish_log.jsonl` + archive.
- **Retry:** on failure the run is `PUBLISH_FAILED`. Next run: if its own validation passes, it publishes its new HTML. If that run cannot build (e.g. source failure), it retries publishing the last validated HTML whose md5 is not yet confirmed in PH. eBay research is not repeated for a publish retry.
- **Credentials:** `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` from environment only (as the existing script). They are never written to files or logs.

---

## 10. CLI, scheduler, tests

| Command | Does | Writes |
|---|---|---|
| `python 10_automation/run.py` | Full daily run S1–S14 | Everything above |
| `python 10_automation/run.py --preflight` | S1 only, plus resolves the configured IDs against the DB (read-only) | `06_validation/<date>/preflight_<run_id>.json` only |
| `python 10_automation/run.py --dry-run` | S1–S10 with DB read-only; **no browser**: research reuses today's/last evidence only, and IDs without it are shown `NOT VERIFIED`; builds and validates in staging | Staging HTML + dry-run validation under `06_validation/<date>/dry_run_*`; **no** status change, **no** local publish, **no** PH write |
| `python 10_automation/run.py --as-of YYYY-MM-DD` | Full run labelled with that date | As full run, under that date |
| `--stage <name>` / `--resume` | Run one stage / continue the last incomplete run | For testing and recovery |

`scheduler.ps1`: parameters `-Time` (default `07:00`, D5) and `-Unregister`. It registers task `KeywordCheckKobiga_Daily` (daily trigger; runs as the current user, only when logged on, because the UK-VPN Chrome runs in the user session). Action: `python "<root>\automation\run.py"`, working dir = project root. No calendar date is hardcoded.

`test_automation.py` covers the Phase 18 list:

- preflight
- unit tests: matcher, n-grams, screen tiers, mapping rule, change detection, status transitions
- DB population test: IDs resolve, read-only
- mapping test
- research evidence test on fixtures: the saved HTML pages from the first real run
- rank reconciliation: builder vs independent validator
- HTML validation
- standalone test
- dry-run
- resume test: kill after N IDs, rerun, and assert completed IDs are not re-researched
- idempotency: run twice and assert no duplicate rows, files or PH records (PH part runs against a **dry-run** transaction that is rolled back)
- scheduler double-registration

The production schedule is registered only after all tests pass (Phase 9 is gated by Phase 10 results).

---

## 11. Decisions needed before Phase 3

| # | Decision | Why it matters | Recommendation |
|---|---|---|---|
| **D1** | **`267765726284` or `267765767284`?** | One ID does not match the old records (digits transposed). If it does not exist in the DB, the source gate stops the whole run. | Confirm the correct ID. I will not change it on my own. |
| **D2** | **Search-term rule for `EBAY_CATEGORY` rows.** The old project found no SOT sub-type for these SKUs, so most or all 12 will likely fall back to the eBay category leaf. Their current categories are: `Ceiling Lights & Chandeliers` (4 IDs, incl. the downlight 267784997642), `Wall Lights` (3), `Lampshades & Lightshades` (2, incl. the wall sconce 267720120199), `Lamps`, `Light Bulbs`, and `Electrical Wires & Cables` (the waste pipe 267791295531). This will be re-checked live in Phase 3. | The approved rule produces terms like "LED Ceiling Lights & Chandeliers", which are broader than the previous report's title-derived terms ("LED Downlight", "LED Pendant Light"). Rows where the listing is in the wrong eBay category (wall sconce under Lampshades, waste pipe under Electrical Wires) will get off-target competitors. | Apply the rule literally: term = `"LED " + leaf`; no "LED" if the leaf already contains it; no "LED" if the category path is outside `Lighting` (so the waste pipe gets "Electrical Wires & Cables"). Show Mapping Source on every row so the effect is visible. Do **not** override from titles. If you want better terms, the right fix is SOT sub-types or correct categories at the source. |
| **D3** | **Linked listings.** The old dashboard listed each product's other listings (same SKU on other marketplaces/accounts) inside the row. | "Only approved Product IDs" could be read as excluding this | Drop linked listings. Show only the approved ID's own marketplace/account/variations. |
| **D4** | **PH audience and versioning.** The old publisher used project_code `KWC`, 8 users (genga, Jarsini, kobiga, powsteena, Sharmilan, Sivajitha, Thasanan, Thinesh), team `ebay_priors`, developer `Apirame`, `version_level` 1, and those rows likely already exist. | The daily publish will **update those same KWC rows** | Keep the same audience and fields in `config.py`. Keep `version_level` fixed; the daily refresh updates `updated_at` and content, and the run_id/date appear inside the HTML. Please confirm the audience list and developer name. |
| **D5** | **Schedule time.** | The UK-VPN Chrome must be running and the user logged on at that time | 07:00 local daily. Please give a time. |
| **D6** | **Seeding from the old project.** Scope now matches the old requested run (11 of 12 IDs). | Seeding gives previous evidence for CARRIED FORWARD labels on day 1 | Start clean. Day 1 research creates the baseline, and the old project stays untouched. |

---

### Decisions recorded (user, 2026-09-22)

| # | Answer |
|---|---|
| D1 | `267765767284` approved; `267765726284` rejected (`scope.json` v2). Preflight 20260922T095034Z-9096: 12/12 found. |
| D2 | Approved: search term = `"LED " + category leaf`; no "LED" if the leaf already contains it or the category path is outside `Lighting`. |
| D3 | Linked listings dropped (user: "Do NOT add linked listings belonging to other Product IDs"). |
| D4 | Confirmed: KWC, 8 users (genga, Jarsini, kobiga, powsteena, Sharmilan, Sivajitha, Thasanan, Thinesh), team `ebay_priors`, developer `Apirame`, `version_level` fixed. |
| D5 | Daily at **08:45** local time. |
| D6 | Import old results as history (user, 2026-09-22). Done by `10_automation/import_history.py`: 12 IDs, 125 files, recompute equal. |

## 12. Pass / fail for Phase 2

- **PASS** if every stage has input, output, validation rule and failure action; scope is config-driven with no population query; publish is gated by local validation; resume and idempotency keys are defined; open decisions are raised.
- **Result:** 14 stages specified; 18 validation checks (16 critical); status model, data layout, PH safety and CLI defined; 6 decisions raised.
- **Next step:** your answers on D1–D6 → Phase 3 (configuration + DB refresh).
