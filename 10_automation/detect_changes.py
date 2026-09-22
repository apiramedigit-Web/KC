"""Stage S4 DETECT CHANGES: compare today's source snapshot with the last successful run's snapshot.

Class per approved Product ID: NEW (not in previous snapshot), CHANGED (a tracked field differs; fields listed),
UNCHANGED, REMOVED (in the previous snapshot but no longer in scope.json). First run: everything NEW.
Research still runs daily for every active, mapped ID (freshness policy: research is refreshed every day);
the classes are recorded in the run summary so a reviewer can see what moved in the source."""
import json

import config as C

TRACKED = ("sku", "product_name", "marketplace", "account", "listing_status", "is_ended", "ebay_category_path", "variation_skus")


def previous_snapshot():
    if not C.LAST_SUCCESS_FILE.exists(): return None, None
    last = json.loads(C.LAST_SUCCESS_FILE.read_text(encoding="utf-8"))
    p = C.ROOT / last["snapshot"] if last.get("snapshot") else None
    return (json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None), last


def compare(prev, snap):
    now = {r["product_id"]: r for r in snap["records"]}
    old = {r["product_id"]: r for r in (prev or {}).get("records", [])}
    out = {}
    for pid, r in now.items():
        if pid not in old: out[pid] = {"class": "NEW"}; continue
        diff = [f for f in TRACKED if json.dumps(r.get(f), default=str) != json.dumps(old[pid].get(f), default=str)]
        out[pid] = {"class": "CHANGED", "fields": diff} if diff else {"class": "UNCHANGED"}
    for pid in old:
        if pid not in now: out[pid] = {"class": "REMOVED"}
    return out
