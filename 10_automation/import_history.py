"""One-time import of the old project's research for the approved Product IDs as HISTORY (user decision D6, 2026-09-22).

Source (read-only, never modified): Keywords check/02_Data/requested/ids/<product_id>.json and the raw files it names
(04_Evidence/search_raw, 04_Evidence/item_raw, 02_Data/item_cache for item captured_at).
Target: 04_research/*/imported_<date>/ and 04_research/keyword_evidence/imported_<date>/<product_id>.json.
The raw files are copied so this project is self-contained and the validator can recount ranks from them.
Imported evidence is labelled origin=IMPORTED with its original capture date. It is only shown on the dashboard
as 'CARRIED FORWARD from <date>' when a day's live research fails - never as CURRENT.
NOTE: the old research used title-derived search terms (e.g. 'LED Wall Light'); the approved rule now uses the
eBay category. Each imported record keeps its old search term and says so.
Keywords and ranks are recomputed with this project's code from the copied raw evidence and compared to the old values.
Idempotent: re-running copies nothing that already exists with the same content and rewrites identical records.

    python 10_automation/import_history.py            # import
    python 10_automation/import_history.py --check    # report only, write nothing
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculate_ranks as R  # noqa: E402
import config as C  # noqa: E402
import extract_keywords as K  # noqa: E402
import research  # noqa: E402

md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()


def _copy(src_rel, dest_dir, report, write):
    src = C.IMPORT_SOURCE / src_rel
    if not src.exists(): report["missing_files"].append(src_rel); return None
    dest = dest_dir / src.name
    if write:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not dest.exists(): shutil.copy2(src, dest); report["copied"] += 1
        elif md5(dest) != md5(src): raise RuntimeError(f"import target differs from source: {dest}")
    return C.rel(dest) if write else str(dest)


def import_one(pid, write, report):
    f = C.IMPORT_SOURCE / "02_Data/requested/ids" / f"{pid}.json"
    if not f.exists(): report["not_available"].append(pid); return None
    old = json.loads(f.read_text(encoding="utf-8"))
    day = old["started_at"][:10]; tag = f"imported_{day}"
    sd, cd, dd = C.SEARCH_RESULTS / tag, C.COMPETITOR_LISTINGS / tag, C.DESCRIPTIONS / tag
    pages = [{**p, "raw_html": _copy(p["raw_html"], sd, report, write) if p.get("raw_html") else None} for p in old["search_evidence"]["pages"]]
    remap = {p0["raw_html"]: p1["raw_html"] for p0, p1 in zip(old["search_evidence"]["pages"], pages) if p0.get("raw_html")}
    comps = []
    for c in old["final_competitors"]:
        ic = C.IMPORT_SOURCE / "02_Data/item_cache" / f"{c['listing_id']}.json"
        cap = json.loads(ic.read_text(encoding="utf-8")).get("captured_at") if ic.exists() else old["started_at"]
        comps.append({**c, "captured_at": cap, "raw_search_page": remap.get(c["raw_search_page"], c["raw_search_page"]),
                      "raw_item_page": _copy(c["raw_item_page"], cd, report, write),
                      "raw_description": _copy(c["raw_description"], dd, report, write) if c.get("raw_description") else None})
    ev = {"product_id": pid, "sku": old.get("sku"), "product_name": old.get("product_name"), "origin": "IMPORTED",
          "imported_from": str(f), "run_id": f"imported-{day}", "run_date": day, "product_subtype": old.get("product_subtype"),
          "mapping_source": f"OLD PROJECT: {old.get('mapping_source')}", "search_term": old["search_term"],
          "search_term_rule": "OLD title-derived rule (superseded 2026-09-22 by SOT -> eBay category rule)",
          "exit_ip": old.get("exit_ip"), "started_at": old["started_at"], "captured_at": old["started_at"], "finished_at": old.get("finished_at"),
          "search_evidence": {"search_capture": None, "captured_at": old["started_at"], "pages": pages, "complete": old["search_evidence"].get("complete")},
          "screening_profile": old["screening_profile"], "candidates": old.get("candidates"), "internal_excluded": old.get("internal_excluded"),
          "tier_counts": old.get("tier_counts"), "shortlist": old.get("shortlist"), "final_competitors": comps,
          "verification_status": research.verification(len(comps)), "research_status": old.get("research_status")}
    if write:
        ev["keywords"] = R.ranks_for(ev, K.keywords_for(ev))
        oldk = {g: [(k["keyword"], k["keyword_rank"]) for k in old["keywords"].get(g, [])] for g in K.GROUPS}
        newk = {g: [(k["keyword"], k["keyword_rank"]) for k in ev["keywords"].get(g, [])] for g in K.GROUPS}
        ev["import_check"] = {"keywords_and_ranks_equal_old_project": oldk == newk, "old": oldk if oldk != newk else "same"}
        report["recompute_equal"][pid] = oldk == newk
        path = C.KEYWORD_EVIDENCE / tag / f"{pid}.json"; C.write_json_atomic(path, ev)
        return {"day": day, "evidence": C.rel(path), "captured_at": old["started_at"], "origin": "IMPORTED", "status": ev["verification_status"]}
    return {"day": day, "status": ev["verification_status"], "competitors": len(comps)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); a = ap.parse_args()
    scope = C.load_scope(); write = not a.check
    report = {"copied": 0, "missing_files": [], "not_available": [], "recompute_equal": {}, "imported": {}}
    st = research.load_status()
    for pid in scope["product_ids"]:
        lv = import_one(pid, write, report)
        if not lv: continue
        report["imported"][pid] = lv
        if write:
            cur = st.setdefault(pid, {})
            prev = cur.get("last_verified")
            if not prev or prev.get("origin") == "IMPORTED": cur["last_verified"] = lv   # never replace LIVE evidence with imported
    if report["missing_files"]: print("MISSING SOURCE FILES - import aborted before status update:", report["missing_files"]); return 1
    if write:
        research.save_status(st)
        out = C.RESEARCH_LOGS / "import_history_report.json"; C.write_json_atomic(out, report); print("report:", C.rel(out))
    print(json.dumps({k: v for k, v in report.items() if k != "imported"}, indent=1))
    for pid, lv in report["imported"].items(): print(pid, lv["status"], lv["day"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
