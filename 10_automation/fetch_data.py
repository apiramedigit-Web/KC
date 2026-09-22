"""Stage S2 FETCH: read the approved Product IDs from the live DB (read-only).

Every query is filtered by the IDs in 10_automation/scope.json; nothing selects the UK population.
SQL lives in 03_sql/fetch_listings.sql and 03_sql/fetch_sot_subtypes.sql.
Reused from the old project (Keywords check/01_Source/build_population_mapping.py): parent-row rule
(is_parent=1 owns the listing), SKU set = parent + variation rows with wrong_sku=0, SOT attribute join."""
import os
import secrets
import time
from datetime import datetime, timezone

import psycopg

import config as C

LISTING_FIELDS = ["item_id", "row_id", "sku", "parent_sku", "title", "site", "status", "is_ended", "end_date", "is_parent", "is_child",
                  "wrong_sku", "sub_source", "account", "ebay_category_path", "category_id", "listing_url", "selected_variations", "created_at", "updated_at"]


def new_run_id(now=None):
    now = now or datetime.now(timezone.utc)
    return f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(2)}"


def connect():
    url = os.environ.get(C.SOURCE_DB_ENV)
    if not url: raise RuntimeError(f"environment variable {C.SOURCE_DB_ENV} is not set")
    err = None
    for attempt in range(C.DB_RETRIES):
        try:
            conn = psycopg.connect(url, connect_timeout=C.DB_CONNECT_TIMEOUT)
            conn.read_only = True
            return conn
        except psycopg.OperationalError as ex:
            err = ex; time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"database not reachable after {C.DB_RETRIES} attempts: {type(err).__name__}")


def _s(v):
    return (v or "").strip()


def fetch(scope, run_date):
    """Return the source snapshot for the approved IDs: one record per ID (found or not)."""
    ids = list(scope["product_ids"])
    fetched_at = datetime.now(timezone.utc)
    with connect() as conn:
        rows = conn.execute((C.SQL_DIR / "fetch_listings.sql").read_text(encoding="utf-8"), {"ids": ids}).fetchall()
        by_id = {}
        for r in rows: by_id.setdefault(_s(r[0]), []).append(dict(zip(LISTING_FIELDS, r)))
        skus = sorted({_s(x["sku"]) for rs in by_id.values() for x in rs
                       if not x["wrong_sku"] and _s(x["sku"]) and _s(x["sku"]).lower() not in C.SKU_PLACEHOLDERS})
        sot = conn.execute((C.SQL_DIR / "fetch_sot_subtypes.sql").read_text(encoding="utf-8"), {"skus": skus, "keys": list(C.SOT_SUBTYPE_KEYS)}).fetchall() if skus else []
    records = []
    for pid in ids:
        rs = by_id.get(pid, [])
        parents = [x for x in rs if x["is_parent"] == 1]
        p = parents[0] if parents else None
        rec = {"product_id": pid, "found": bool(rs), "row_count": len(rs), "parent_rows": len(parents)}
        if p:
            rec.update(sku=_s(p["sku"]), product_name=_s(p["title"]), marketplace=_s(p["site"]), account=_s(p["account"]) or None,
                       sub_source=p["sub_source"], listing_status=_s(p["status"]), is_ended=p["is_ended"], end_date=p["end_date"],
                       ebay_category_path=_s(p["ebay_category_path"]) or None, category_id=_s(p["category_id"]) or None, listing_url=_s(p["listing_url"]) or None,
                       source_updated_at=p["updated_at"], source_created_at=p["created_at"])
        rec["variation_skus"] = sorted({_s(x["sku"]) for x in rs if x["is_child"] == 1 and not x["wrong_sku"] and _s(x["sku"])})
        rec["listing_skus"] = sorted({_s(x["sku"]) for x in rs if not x["wrong_sku"] and _s(x["sku"]) and _s(x["sku"]).lower() not in C.SKU_PLACEHOLDERS})
        records.append(rec)
    return {"_meta": {"fetched_at": fetched_at.isoformat(), "run_date": run_date, "scope_version": scope.get("version"), "approved_ids": ids,
                      "source": f"env {C.SOURCE_DB_ENV} (read-only)", "queries": ["03_sql/fetch_listings.sql", "03_sql/fetch_sot_subtypes.sql"],
                      "db_rows": len(rows), "sot_rows": len(sot)},
            "records": records,
            "sot": [{"sku": s, "key": k, "value": v, "updated_at": u} for s, k, v, u in sot]}


def is_active(rec):
    return rec.get("found") and rec.get("listing_status") == "Active" and not rec.get("is_ended")
