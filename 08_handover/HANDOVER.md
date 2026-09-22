# Handover: Keyword Check – Kobiga Daily Automation

| Field | Value |
|---|---|
| Objective | Refresh the Keyword Check daily from the live database, for the 12 approved Product IDs only, and keep the standalone dashboard and the PH Dashboard at the latest validated version |
| Requirement | `00_requirements/System Task - Keyword check- Kobiga.csv` (output columns, Rank definition) · method `00_requirements/Keyword Analysis.pdf` |
| Owner / requester | Kobiga |
| Status (2026-09-22) | **Built, tested, scheduled.** Local pipeline verified end-to-end. **PH push not yet performed** (see Blockers). |
| Next scheduled run | 2026-09-23 08:45 (task `KeywordCheckKobiga_Daily`) |
| How it works | `10_automation/README.md` |

## 1. What was done

1. Asset inventory of the old project (`10_automation/asset_inventory.md`): 25 scripts classified; 7 reused or extended; 17 not used.
2. Workflow design with 14 stages (`10_automation/WORKFLOW_DESIGN.md`). Decisions D1–D6 are recorded there.
3. Scope fixed in `10_automation/scope.json` v2 (12 IDs). `267765726284` is rejected; `267765767284` is approved.
4. Read-only preflight: 12/12 IDs found. The SOT holds no sub-type for any of their 25 SKUs, so all 12 are mapped from the eBay category.
5. One-time import of the old project's research as history: 125 raw files copied (the old project was only read). Recomputing keywords and ranks with the new code matched the old values exactly for all 12 IDs.
6. The full pipeline was implemented, with 21 offline tests.

## 2. Verification evidence

| Claim | Evidence | Status |
|---|---|---|
| 12 approved IDs resolve in the DB | `06_validation/2026-09-22/preflight_*.json` | VERIFIED |
| Tests pass (scope guard, mapping, matcher, extraction, builder-vs-validator recount, change detection, resume after crash, CAPTCHA handling, UK-exit failure, publish refusal, PH pending/retry, lock, deterministic build, tampered rank / extra ID / false CURRENT detected) | `python 10_automation/test_automation.py` → 21 OK | VERIFIED |
| Dry run passes validation | `06_validation/2026-09-22/dry_run_validation_*.json` | VERIFIED |
| Manual full run (without PH) validates and publishes locally | `05_evidence/research_logs/2026-09-22/run_summary_*.json` → `LOCAL_PUBLISHED_PH_SKIPPED`; `06_validation/2026-09-22/local_validation_*.json` 0 critical failures | VERIFIED |
| Rerun is idempotent | Second run: 12 rows, 60 competitors, 118 keywords, all unique; 12 status entries | VERIFIED |
| Publish protection | A run whose validated hash did not match was **refused** and the live file was untouched (run `20260922T101300Z-9d4f`, bug since fixed); unit test covers it | VERIFIED |
| Scheduler | `10_automation/scheduler.ps1 -Status`: daily 08:45, one task after repeated registration | VERIFIED |
| Live eBay research by the automation | Not yet run: UK-VPN Chrome (CDP 9222) was not running on 2026-09-22 | **UNPROVEN until the first run with the browser up** |
| PH Dashboard push | Credentials set and dry run OK (would update 8 KWC rows, insert 0); first real push scheduled for the 2026-09-23 08:45 run by owner decision | **UNPROVEN until that run** |

## 3. Current dashboard content

All 12 rows currently show **CARRIED FORWARD from 2026-09-22 (imported from old project)**. That is the old project's verified research, clearly dated, and it used the old title-derived search terms. The first run with the UK-VPN Chrome available replaces each row with live research using the approved category-based search terms, labelled **CURRENT**.

## 4. Blockers / actions for the owner

1. **PH credentials: DONE (2026-09-22).** `temp_user` is saved as Windows user environment variables. Read-only access is verified (8 KWC rows), and the PH dry run would update 8 rows and insert 0.
2. **UK-VPN Chrome at 08:45:** Chrome must be running with remote debugging on `127.0.0.1:9222` and the VPN set to the United Kingdom. Otherwise research is retried the next day and rows stay CARRIED FORWARD.
3. **First PH publish:** the owner decided on 2026-09-22 to keep today's PH content and let the **2026-09-23 08:45 run** do the first push. That run updates only the 8 `KWC` rows (genga, Jarsini, kobiga, powsteena, Sharmilan, Sivajitha, Thasanan, Thinesh). Check `05_evidence/database/ph_publish_log.jsonl` for a `PUBLISHED` entry.

## 5. Known limits

- All 12 search terms come from eBay categories (the SOT has no sub-type for these SKUs). Some are broad ("LED Ceiling Lights & Chandeliers") and two listings are in misleading categories (the wall sconce 267720120199 under Lampshades & Lightshades; the waste pipe 267791295531 under Electrical Wires & Cables). The fix belongs at the source (SOT or listing category), not in the automation.
- Three parent rows have the SKU placeholder `sku not assigneds` (267791295531, 267765767284, 267687534749). It is shown as stored in the DB, with the real variation SKUs under it.
- Last 30 Days Sales: always NOT VERIFIED (eBay sign-in CAPTCHA).
- GitHub: https://github.com/apiramedigit-Web/KC (branch `main`, public). The daily run does not commit or push automatically; commit the day's evidence manually when needed.

## 6. Do not touch

- `C:\Users\LED 222\Keywords check\` (old project: read-only reference)
- Folder names `00_requirements` … `11_archive`: all code paths come from `10_automation/config.py` (`F`). Rename a folder only there, then re-run `10_automation\scheduler.ps1` and the tests. (The duplicate copy of the old project was removed on 2026-09-22; see root `README.md`, "Structure history".)
- `tech_team_outputs.ph_task` rows other than `project_code = 'KWC'`
- `07_report/keyword_check_kobiga.html`: never hand-edit; it is regenerated by `run.py`

## 7. Next action

Check the result of the 2026-09-23 08:45 run in `05_evidence/research_logs/2026-09-23/run_summary_*.json`.
