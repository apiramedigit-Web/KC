# Prompt Register: Keyword Check – Kobiga

| Field | Value |
|---|---|
| Purpose | Mini-AIOS Skill 12 ("prompt used for important execution" must be saved): the instructions that drove each phase, what they decided, and where the resulting assets are |
| Owner | Kobiga |
| Note | These are summaries of the instructions given in the Claude Code session of 2026-09-22 (the full texts were pasted in chat and are not stored verbatim here). Binding decisions are quoted exactly. |

| # | Date | Prompt | Key instructions / decisions | Resulting assets |
|---|---|---|---|---|
| P1 | 2026-09-22 | Folder-structure setup | Create `Keyword_Check_Kobiga/` with the AIOS folders and README only; no research, DB or eBay work; do not modify the old project | Folder tree, `README.md`, `00_requirements/` copies |
| P2 | 2026-09-22 | Automation task, Phase 1 | Convert the Keyword Check into a daily automated workflow; first inspect existing assets (Reuse → Extend → Merge → Create New); old project read-only | `10_automation/asset_inventory.md` |
| P3 | 2026-09-22 | Scope confirmation, Phase 2 | "The automation scope is ONLY the specific Product IDs that I have explicitly provided"; SOT sub-type, else eBay category ("YES — eBay category is explicitly approved as the fallback"); no title inference; local validation before PH push | `10_automation/WORKFLOW_DESIGN.md` |
| P4 | 2026-09-22 | Final approved scope | "Use 267765767284. Do NOT use 267765726284." Read-only preflight of all 12 IDs, then wait | `10_automation/scope.json` v2; `06_validation/2026-09-22/preflight_20260922T095034Z-9096.json` |
| P5 | 2026-09-22 | Decisions D2–D6 | Search-term rule OK; PH audience confirmed; "daily 8.45 a.m"; import the old results; "complete the automation work now" | `10_automation/*.py`, `scheduler.ps1`, `test_automation.py`, `import_history.py`, `10_automation/README.md`, `08_handover/HANDOVER.md` |
| P6 | 2026-09-22 | AIOS folder review (screenshot) | Maintain the proper AIOS folder structure per the Mini-AIOS guide; decision: keep the copied `00_…05_` folders as they are | `README.md` folder map + legacy note, this register, `09_closure/CLOSURE_2026-09-22.md` |
| P8 | 2026-09-22 | PH credentials + first push | `temp_user` credentials supplied (`Downloads\temp_user (1) 2 (1).py`, not run) → saved as Windows user env vars PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD. Read-only check: 8 KWC rows exist. PH dry run: would update 8, insert 0. Decision: "ipo irukira dashboard ok athu tommarow la irunthu daily update aana ok" (the current PH dashboard is fine; the daily updates from tomorrow are OK). **No push today.** | `05_evidence/database/ph_publish_log.jsonl` (DRY_RUN entry) |
| P9 | 2026-09-22 | VPN-off handling | "rendu fix um add pannu, 10:45 12:45 14:45 ok" (add both fixes; 10:45 12:45 14:45 OK): (1) VPN/browser/CAPTCHA problems end with a clear status and exit 4; (2) same-day retry slots 10:45, 12:45, 14:45 | `10_automation/run.py` (`research_problem`, `already_complete`, `EXIT`), `10_automation/scheduler.ps1` (4 triggers), 3 new tests |
| P7 | 2026-09-22 | Structure: no duplicates, numbered folders | "duplicate aa folders illaama no podu structure maintain pannu" (keep the structure without duplicate folders, with numbered folders); option chosen: "Numbered folders" | Duplicate copy removed (md5-verified first); folders renamed `00_requirements` … `11_archive`; `10_automation/config.py` `F`; scheduler re-registered; README "Structure history" |

## How to add an entry

For every new instruction that changes scope, method, schedule or publishing, add a row with the date, the exact decision wording, and the asset path it produced. Change the scope only in `10_automation/scope.json` (with a new `version` and `change_note`), then reference that version here.
