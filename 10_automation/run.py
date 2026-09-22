"""Keyword Check - Kobiga daily automation: runs stages S1-S14 (see 10_automation/WORKFLOW_DESIGN.md).

    python 10_automation/run.py                     # full daily run (scheduled 08:45 by scheduler.ps1)
    python 10_automation/run.py --preflight         # config + DB + browser + PH checks, 12-ID verification; no research, no publish
    python 10_automation/run.py --dry-run           # DB read, mapping, build + validate in staging; no browser, no status change, no publish
    python 10_automation/run.py --as-of 2026-09-23  # full run labelled with that date (DB is still read live)
    python 10_automation/run.py --no-research       # skip eBay (rows use last verified evidence, labelled CARRIED FORWARD)
    python 10_automation/run.py --no-ph             # everything except the PH Dashboard push
Exit codes: 0 SUCCESS / SUCCESS_WITH_CARRIED_FORWARD / preflight or dry-run OK; 2 PUBLISH_FAILED; 3 ALREADY_RUNNING; 1 any other failure."""
import argparse
import ctypes
import json
import os
import sys
import traceback
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402
import calculate_ranks  # noqa: E402
import config as C  # noqa: E402
import detect_changes  # noqa: E402
import extract_keywords  # noqa: E402
import fetch_data  # noqa: E402
import generate_dashboard  # noqa: E402
import logger as L  # noqa: E402
import map_products  # noqa: E402
import publish  # noqa: E402
import research  # noqa: E402
import validate_dashboard  # noqa: E402
import validate_data  # noqa: E402


# ---------------------------------------------------------------- lock
def _pid_alive(pid):
    if os.name != "nt":
        try: os.kill(pid, 0); return True
        except OSError: return False
    k = ctypes.windll.kernel32; h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h: return False
    code = ctypes.c_ulong(); k.GetExitCodeProcess(h, ctypes.byref(code)); k.CloseHandle(h)
    return code.value == 259                                              # STILL_ACTIVE


def acquire_lock(run_id):
    C.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if C.LOCK_FILE.exists():
        try: held = json.loads(C.LOCK_FILE.read_text(encoding="utf-8"))
        except Exception: held = {"pid": -1}
        if _pid_alive(held.get("pid", -1)): return held
        C.LOCK_FILE.unlink()                                               # stale lock: owner process is gone
    fd = os.open(C.LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, json.dumps({"pid": os.getpid(), "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat()}).encode()); os.close(fd)
    return None


def release_lock():
    try: C.LOCK_FILE.unlink()
    except FileNotFoundError: pass


# ---------------------------------------------------------------- stages
def preflight_checks(scope_ok, scope_err):
    out = {"scope": "OK" if scope_ok else f"FAIL: {scope_err}", "source_db_env": bool(os.environ.get(C.SOURCE_DB_ENV)),
           "ph_env": [v for v in C.PH_DB_ENVS if not os.environ.get(v)] or "OK"}
    try:
        with urllib.request.urlopen(C.CDP_URL.rstrip("/") + "/json/version", timeout=5) as r: out["browser_cdp"] = "OK" if r.status == 200 else f"HTTP {r.status}"
    except Exception as ex:
        out["browser_cdp"] = f"NOT REACHABLE ({type(ex).__name__})"
    for d in (C.DB_EVIDENCE, C.VALIDATION, C.RESEARCH_LOGS, C.STAGING):
        d.mkdir(parents=True, exist_ok=True)
    return out


def keywords_stage(day):
    """S7 + S8 for every Product ID whose evidence for this day is LIVE (imported/carried evidence is left as captured)."""
    done = []
    for f in sorted((C.KEYWORD_EVIDENCE / day).glob("*.json")) if (C.KEYWORD_EVIDENCE / day).exists() else []:
        ev = json.loads(f.read_text(encoding="utf-8"))
        if ev.get("origin") != "LIVE": continue
        ev["keywords"] = calculate_ranks.ranks_for(ev, extract_keywords.keywords_for(ev))
        C.write_json_atomic(f, ev); done.append(ev["product_id"])
    return done


def final_status(research_out, ds, local, ph, dry):
    if dry: return "DRY_RUN_OK"
    if local.get("result") != "PUBLISHED": return "PUBLISH_LOCAL_FAILED"
    if ph and ph.get("result") not in ("PUBLISHED", "PUBLISH_SKIPPED_UNCHANGED"): return "PUBLISH_FAILED"
    if any(r["freshness"] != "CURRENT" for r in ds["rows"]): return "SUCCESS_WITH_CARRIED_FORWARD"
    return "SUCCESS"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--as-of", type=date.fromisoformat); ap.add_argument("--no-research", action="store_true"); ap.add_argument("--no-ph", action="store_true")
    a = ap.parse_args(argv)
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # scheduled task console may be cp1252
    except Exception: pass
    day = (a.as_of or date.today()).isoformat()
    run_id = fetch_data.new_run_id()
    kind = "preflight" if a.preflight else ("dry_run" if a.dry_run else "run")
    held = acquire_lock(run_id)
    if held:
        print(f"ALREADY_RUNNING: run {held.get('run_id')} (pid {held.get('pid')}) holds {C.rel(C.LOCK_FILE)}"); return 3
    log = L.setup(run_id, day, kind)
    summary = {"run_id": run_id, "run_type": kind, "run_date": day, "run_started_at": datetime.now(timezone.utc).isoformat(), "stages": {}, "status": None}
    sfile = C.RESEARCH_LOGS / day / f"{kind}_summary_{run_id}.json"
    try:
        # S1 PREFLIGHT
        try: scope = C.load_scope(); scope_ok, err = True, None
        except Exception as ex: scope, scope_ok, err = None, False, str(ex)
        summary["stages"]["preflight"] = pf = preflight_checks(scope_ok, err); L.event("PREFLIGHT", "DONE", **{k: v for k, v in pf.items()})
        if not scope_ok or not pf["source_db_env"]:
            summary["status"] = "PREFLIGHT_FAILED"; return 1
        summary["approved_ids"] = scope["product_ids"]; summary["scope_version"] = scope["version"]
        # S2 FETCH
        snap = fetch_data.fetch(scope, day); snap["_meta"]["run_id"] = run_id
        snap_path = C.unique_path(C.DB_EVIDENCE / day / f"source_snapshot_{'' if kind == 'run' else kind + '_'}{run_id}.json")
        C.write_json_atomic(snap_path, snap)
        recs = snap["records"]
        summary["stages"]["fetch"] = {"snapshot": C.rel(snap_path), "db_fetched_at": snap["_meta"]["fetched_at"], "db_rows": snap["_meta"]["db_rows"],
                                      "found": sum(r["found"] for r in recs), "unique_skus": len({r.get("sku") for r in recs if r["found"]})}
        # S3 VALIDATE SOURCE
        checks, per = validate_data.source_checks(snap)
        crit = validate_data.critical_failures(checks)
        summary["stages"]["validate_source"] = {"overall": "FAIL" if crit else "PASS", "checks": checks, "per_id_issues": per}
        L.event("VALIDATE_SOURCE", "FAIL" if crit else "PASS", issues={k: v for k, v in per.items() if v})
        # S5 MAP (needed by preflight too)
        mapping = map_products.map_all(snap)
        map_path = C.unique_path(C.PRODUCT_MAPPING / day / f"mapping_{'' if kind == 'run' else kind + '_'}{run_id}.csv"); map_products.write_csv(mapping, map_path)
        term_path = C.unique_path(C.KEYWORD_MAPPING / day / f"search_terms_{'' if kind == 'run' else kind + '_'}{run_id}.csv"); map_products.write_csv(mapping, term_path, map_products.TERM_COLUMNS)
        summary["stages"]["map"] = {"mapping": C.rel(map_path), "search_terms": C.rel(term_path),
                                    "per_id": {m["product_id"]: {k: m[k] for k in ("product_subtype", "mapping_source", "mapping_status", "search_term")} for m in mapping}}
        if a.preflight:
            vp = C.unique_path(C.VALIDATION / day / f"preflight_{run_id}.json")
            C.write_json_atomic(vp, {**summary, "overall": "FAIL" if crit else "PASS"}); summary["status"] = "PREFLIGHT_FAILED" if crit else "PREFLIGHT_OK"
            for r, m in zip(recs, mapping):
                print(" | ".join(str(x) for x in (r["product_id"], r["found"], r.get("sku"), r.get("marketplace"), r.get("account"), r.get("listing_status"), m["mapping_source"], m["product_subtype"], m["search_term"])))
            print("browser:", pf["browser_cdp"], "| PH credentials missing:" if pf["ph_env"] != "OK" else "| PH credentials: OK", pf["ph_env"] if pf["ph_env"] != "OK" else "")
            return 0 if not crit else 1
        if crit:
            summary["status"] = "SOURCE_FAILED"
            if not a.dry_run and not a.no_ph: summary["stages"]["ph_retry"] = publish.publish_ph(run_id)   # retry a pending validated version, if any
            return 1
        # S4 DETECT CHANGES
        prev, last = detect_changes.previous_snapshot()
        changes = detect_changes.compare(prev, snap)
        summary["stages"]["changes"] = {"previous_run": (last or {}).get("run_id"), "classes": changes}
        # S6 RESEARCH
        with fetch_data.connect() as conn:
            rout = research.run(snap, mapping, day, run_id, conn, dry_run=a.dry_run or a.no_research)
        summary["stages"]["research"] = rout
        # S7 + S8
        if not a.dry_run: summary["stages"]["keywords"] = {"recomputed_live": keywords_stage(day)}
        # S9 BUILD
        ds = generate_dashboard.build_dataset(snap, mapping, day, run_id, changes)
        staged = generate_dashboard.build(ds, f"{kind}_{run_id}" if kind != "run" else run_id)
        summary["stages"]["build"] = {"staged": C.rel(staged), "rows": len(ds["rows"]),
                                      "freshness": {r["product_id"]: r["freshness"] for r in ds["rows"]}}
        # S10 VALIDATE OUTPUT
        val = validate_dashboard.validate(staged, scope, day, run_id)
        vpath = C.unique_path(C.VALIDATION / day / f"{'local_validation' if kind == 'run' else 'dry_run_validation'}_{run_id}.json"); C.write_json_atomic(vpath, val)
        summary["stages"]["validate_output"] = {"overall": val["overall"], "critical_failures": val["critical_failures"], "warnings": val["warnings"], "result": C.rel(vpath),
                                                "failed": [c["check"] for c in val["checks"] if c["result"] == "FAIL"]}
        L.event("VALIDATE_OUTPUT", val["overall"], critical=val["critical_failures"], warnings=val["warnings"])
        if a.dry_run:
            if val["overall"] == "PASS": staged.unlink()                       # a failed dry-run keeps its page for inspection
            summary["status"] = "DRY_RUN_OK" if val["overall"] == "PASS" else "DRY_RUN_FAILED"; return 0 if val["overall"] == "PASS" else 1
        if val["overall"] != "PASS":
            summary["status"] = "VALIDATION_FAILED"
            if not a.no_ph: summary["stages"]["ph_retry"] = publish.publish_ph(run_id)
            return 1
        # S11 PUBLISH LOCAL
        local = publish.publish_local(staged, val); summary["stages"]["publish_local"] = local; L.event("PUBLISH_LOCAL", local["result"])
        ph = None
        if local["result"] == "PUBLISHED":
            publish.mark_pending(val, run_id, ds)
            C.write_json_atomic(C.LAST_SUCCESS_FILE, {"run_id": run_id, "run_date": day, "snapshot": C.rel(snap_path), "html_md5": val["html_md5"], "validation": C.rel(vpath)})
            staged.unlink()
            # S12 PUBLISH PH
            ph = {"result": "SKIPPED (--no-ph)"} if a.no_ph else publish.publish_ph(run_id)
            summary["stages"]["publish_ph"] = ph; L.event("PUBLISH_PH", ph["result"], error=ph.get("error"))
        summary["status"] = final_status(rout, ds, local, None if a.no_ph else ph, False)
        if a.no_ph and local.get("result") == "PUBLISHED": summary["status"] = "LOCAL_PUBLISHED_PH_SKIPPED"   # PH stays pending for the next run
        # S13 ARCHIVE
        summary["run_completed_at"] = datetime.now(timezone.utc).isoformat()
        built = {"dashboard.html": C.REPORT} if local.get("result") == "PUBLISHED" else {"dashboard_not_published.html": staged}   # never file the previous live page under this run
        adir, _ = archive.archive(day, run_id, {"scope.json": C.SCOPE_FILE, "source_snapshot.json": snap_path, "mapping.csv": map_path, "search_terms.csv": term_path,
                                                **built, "local_validation.json": vpath}, ds, {"run_summary.json": summary, "ph_publish.json": ph or {}})
        summary["stages"]["archive"] = adir
        return {"SUCCESS": 0, "SUCCESS_WITH_CARRIED_FORWARD": 0, "LOCAL_PUBLISHED_PH_SKIPPED": 0, "PUBLISH_FAILED": 2}.get(summary["status"], 1)
    except Exception as ex:
        summary["status"] = summary["status"] or "ABORTED"; summary["error"] = f"{type(ex).__name__}: {ex}"; summary["traceback"] = traceback.format_exc()
        log.error(summary["traceback"]); return 1
    finally:
        summary.setdefault("run_completed_at", datetime.now(timezone.utc).isoformat())
        C.write_json_atomic(sfile, summary)
        L.event("RUN", summary["status"], summary=C.rel(sfile))
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
