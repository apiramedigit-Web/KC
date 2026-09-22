"""Stage S3 VALIDATE SOURCE and the per-ID research gate (S6).

Source gate: every approved Product ID must resolve to exactly one parent row. A missing ID is critical
(the run stops - no dashboard is built with a silently missing ID). Other field problems are recorded per ID.
Research gate: GB exit, search filters, evidence files present for every final competitor."""
import config as C


def _ck(checks, name, ok, critical, detail=""):
    checks.append({"check": name, "result": "PASS" if ok else "FAIL", "critical": critical, "detail": detail})


def source_checks(snap):
    """Returns (checks, per_id_issues)."""
    checks, per = [], {}
    recs = snap["records"]; ids = snap["_meta"]["approved_ids"]
    missing = [r["product_id"] for r in recs if not r["found"]]
    _ck(checks, "Every approved Product ID found in listings.ebay_listings", not missing, True, missing)
    _ck(checks, "Approved IDs returned = approved list (no extra, none missing)", [r["product_id"] for r in recs] == ids and len(set(ids)) == len(ids), True)
    no_parent = [r["product_id"] for r in recs if r["found"] and r["parent_rows"] != 1]
    _ck(checks, "Exactly one parent row (is_parent=1) per found ID", not no_parent, True, no_parent)
    for r in recs:
        issues = []
        if not r["found"]: per[r["product_id"]] = ["NOT FOUND"]; continue
        if r["parent_rows"] != 1: issues.append(f"{r['parent_rows']} parent rows")
        if not r.get("sku") or r["sku"].lower() in C.SKU_PLACEHOLDERS: issues.append(f"SKU placeholder/empty on parent row ({r.get('sku')!r})")
        if not r.get("product_name"): issues.append("no title")
        if not r.get("account"): issues.append("account not resolved from sub_source")
        if r.get("marketplace") != "UK": issues.append(f"marketplace {r.get('marketplace')}")
        if r.get("listing_status") != "Active" or r.get("is_ended"): issues.append(f"listing status {r.get('listing_status')}, is_ended={r.get('is_ended')}")
        per[r["product_id"]] = issues
    return checks, per


def critical_failures(checks):
    return [c for c in checks if c.get("critical") and c["result"] == "FAIL"]


def research_gate(ev):
    """Checks one Product ID's research evidence. Returns list of problems (empty = OK)."""
    probs = []
    if (ev.get("exit_ip") or {}).get("country") != C.REQUIRED_EXIT_COUNTRY: probs.append("exit country not GB")
    for p in (ev.get("search_evidence") or {}).get("pages", []):
        if not all(f in p["url"] for f in C.SEARCH_FILTERS): probs.append(f"search page {p['page']} missing filters")
    for c in ev.get("final_competitors", []):
        for k in ("raw_search_page", "raw_item_page"):
            if not c.get(k) or not (C.ROOT / c[k]).exists(): probs.append(f"{c['listing_id']}: {k} missing")
        if c.get("raw_description") and not (C.ROOT / c["raw_description"]).exists(): probs.append(f"{c['listing_id']}: raw_description missing")
    return probs
