"""Stages S11 PUBLISH LOCAL and S12 PUBLISH PH.

LOCAL: the staged HTML replaces 07_report/keyword_check_kobiga.html atomically (os.replace) ONLY if its md5 equals the
md5 that validation passed. Otherwise nothing changes.
PH: tech_team_outputs.ph_task, rows with project_code KWC only. Upsert on (project_code, assigned_user) for the
confirmed audience, in ONE transaction (all rows or none), with a KWC-scoped row-count guard, then verified from a
fresh connection by md5(html_content). Content = the validated live local HTML (never unvalidated data, never the DB
directly). Unchanged content (every KWC row already has this md5) -> PUBLISH_SKIPPED_UNCHANGED (no write).
Credentials: PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD from the environment only.
State (for next-run retry): 05_evidence/research_logs/ph_state.json. Every attempt: 05_evidence/database/ph_publish_log.jsonl.
Reused from Keywords check/01_Source/publish_ph_task.py (upsert, guard, verify pattern)."""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

import config as C

PH_STATE = C.RESEARCH_LOGS / "ph_state.json"
md5_of = lambda p: hashlib.md5(p.read_bytes()).hexdigest()
now = lambda: datetime.now(timezone.utc).isoformat()


def publish_local(staged, validation):
    if validation.get("overall") != "PASS": return {"result": "REFUSED", "reason": "validation did not pass"}
    digest = md5_of(staged)
    if digest != validation.get("html_md5"): return {"result": "REFUSED", "reason": "staged file differs from the validated file"}
    C.REPORT.parent.mkdir(parents=True, exist_ok=True)
    tmp = C.REPORT.with_name(C.REPORT.name + ".tmp"); shutil.copyfile(staged, tmp)
    os.replace(tmp, C.REPORT)
    ok = md5_of(C.REPORT) == digest
    return {"result": "PUBLISHED" if ok else "FAILED", "path": C.rel(C.REPORT), "md5": digest, "at": now()}


def load_state():
    return json.loads(PH_STATE.read_text(encoding="utf-8")) if PH_STATE.exists() else {}


def mark_pending(validation, run_id, dataset):
    """Record that this validated live HTML must reach PH (cleared when a publish is confirmed)."""
    st = load_state()
    st["pending"] = {"run_id": run_id, "md5": validation["html_md5"], "ids": dataset["_meta"]["approved_ids"], "since": now(),
                     "description": description(dataset)}
    C.write_json_atomic(PH_STATE, st)


def description(ds):
    rows = ds["rows"]; ver = sum(r["verification_status"] == "VERIFIED" for r in rows)
    cur = sum(r["freshness"] == "CURRENT" for r in rows)
    kws = sum(len(v) for r in rows for v in r["keywords"].values()); comps = sum(len(r["final_competitors"]) for r in rows)
    return (f"Keyword Check for {len(rows)} approved eBay UK Product IDs, refreshed daily (run {ds['_meta']['run_id']}, {ds['_meta']['run_date']}). "
            f"Requirement columns: SKU, Product ID, Product Name, Primary / Secondary / Long-Tail / Competitor Keywords, each with its own Keyword Rank "
            f"(= how many of that listing's verified competitors use the keyword in their title or description). eBay UK research through a UK VPN "
            f"(Buy It Now, New, UK only, result pages 1-3, own accounts excluded): {comps} competitor listings, {kws} keywords, {ver} of {len(rows)} IDs verified, "
            f"{cur} researched today, {len(rows) - cur} carried forward or not verified (dated in the dashboard). Competitor 30-day sales NOT VERIFIED (eBay sign-in CAPTCHA, not bypassed).")


def _log(rec):
    C.PH_PUBLISH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(C.PH_PUBLISH_LOG, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def publish_ph(run_id, dry=False):
    """Publish the live local HTML if it is the pending validated version. Returns the result record."""
    st = load_state(); pend = st.get("pending")
    rec = {"at": now(), "run_id": run_id, "dry_run": dry}
    if not pend:
        rec.update(result="NOTHING_PENDING"); return rec
    rec.update(pending_run_id=pend["run_id"], md5=pend["md5"], product_ids=pend["ids"])
    if not C.REPORT.exists() or md5_of(C.REPORT) != pend["md5"]:
        rec.update(result="REFUSED", error="live local HTML is not the validated pending version"); _log(rec); return rec
    missing = [v for v in C.PH_DB_ENVS if not os.environ.get(v)]
    if missing:
        rec.update(result="FAILED", error=f"PH credentials not set in the environment: {missing}"); _log(rec); return rec
    html = C.REPORT.read_text(encoding="utf-8"); P = C.PH
    import psycopg
    dsn = dict(host=os.environ["PGHOST"], port=os.environ["PGPORT"], dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
               password=os.environ["PGPASSWORD"], connect_timeout=C.DB_CONNECT_TIMEOUT)
    try:
        with psycopg.connect(**dsn) as conn, conn.cursor() as cur:
            cur.execute("select id, assigned_user, md5(html_content) from tech_team_outputs.ph_task where project_code=%s", (P["project_code"],))
            existing = {u: (i, m) for i, u, m in cur.fetchall()}; before = len(existing)
            if all(u in existing and existing[u][1] == pend["md5"] for u in P["users"]):
                rec.update(result="PUBLISH_SKIPPED_UNCHANGED", rows=before); conn.rollback()
            elif dry:
                rec.update(result="DRY_RUN", would_update=[u for u in P["users"] if u in existing], would_insert=[u for u in P["users"] if u not in existing]); conn.rollback()
            else:
                upd, ins = [], []
                for u in P["users"]:
                    tid = f"kwc_{u}_keyword_check_V{P['version_level']:03d}"
                    if u in existing:
                        cur.execute("""update tech_team_outputs.ph_task set project_name=%s, task_name=%s, task_id=%s, team=%s, developer=%s, html_content=%s,
                                       description=%s, phase_level=%s, version_level=%s, version_status=%s, assigned_user_team=%s, updated_at=now()
                                       where project_code=%s and assigned_user=%s""",
                                    (P["project_name"], P["task_name"], tid, P["team"], P["developer"], html, pend["description"], P["phase_level"],
                                     P["version_level"], P["version_status"], P["assigned_user_team"], P["project_code"], u)); upd.append(u)
                    else:
                        cur.execute("""insert into tech_team_outputs.ph_task (project_name, project_code, task_name, task_id, team, developer, assigned_user, html_content,
                                       description, phase_level, version_level, version_status, assigned_user_team) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                    (P["project_name"], P["project_code"], P["task_name"], tid, P["team"], P["developer"], u, html, pend["description"],
                                     P["phase_level"], P["version_level"], P["version_status"], P["assigned_user_team"])); ins.append(u)
                cur.execute("select count(*) from tech_team_outputs.ph_task where project_code=%s", (P["project_code"],))
                after = cur.fetchone()[0]; expected = before + len(ins)
                if after != expected:
                    conn.rollback(); rec.update(result="FAILED", error=f"KWC row count {after}, expected {expected}; rolled back")
                else:
                    conn.commit(); rec.update(updated=upd, inserted=ins)
        if rec.get("result") is None:
            with psycopg.connect(**dsn) as conn:
                rows = conn.execute("select assigned_user, md5(html_content), developer from tech_team_outputs.ph_task where project_code=%s", (P["project_code"],)).fetchall()
            got = {u: m for u, m, _ in rows}
            ok = all(got.get(u) == pend["md5"] for u in P["users"])
            rec.update(result="PUBLISHED" if ok else "FAILED", verified_rows=sum(got.get(u) == pend["md5"] for u in P["users"]),
                       error=None if ok else "md5 verification from a fresh connection failed")
    except Exception as ex:
        rec.update(result="FAILED", error=f"{type(ex).__name__}: {str(ex)[:300]}")
    if rec["result"] in ("PUBLISHED", "PUBLISH_SKIPPED_UNCHANGED") and not dry:
        st["confirmed"] = {"md5": pend["md5"], "run_id": pend["run_id"], "at": rec["at"]}; st.pop("pending", None)
        C.write_json_atomic(PH_STATE, st)
    _log(rec)
    return rec
