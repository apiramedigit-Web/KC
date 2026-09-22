"""Stage S5 MAP: Product/Sub-Type, Mapping Source and Search Term for each approved Product ID.

Sub-type rule (user, 2026-09-22):
  1. SOT Product/Sub-Type: configurator.components_sot_* attribute 'product_subtype', else 'sub_type',
     over the listing's own SKUs (parent + variation rows, wrong_sku=0). Values containing '[VERIFY' are
     ignored. Most common value wins; ties alphabetical.                      -> Mapping Source SOT_SUBTYPE
  2. Else the listing's eBay category leaf (last ':' segment of product_type) -> Mapping Source EBAY_CATEGORY
  3. Else                                                                     -> Mapping Status NOT VERIFIED
  The title is NEVER used to infer a sub-type.
Search term (Keyword Analysis.pdf Step 2 'Product Sub-Type + LED'; rule D2 approved 2026-09-22):
  "LED " + sub-type, except: no prefix if the sub-type already contains the word LED, and no prefix if the
  listing's eBay category path is outside Lighting (the LED rule is for lighting products). Wording kept as is.
Reused from the old project: SOT clean/priority rule of Keywords check/01_Source/build_population_mapping.py."""
import csv
import re
from collections import Counter

import config as C


def _clean(v):
    return None if not v or not v.strip() or "[VERIFY" in v else v.strip()


def sot_by_sku(sot_rows):
    """sku -> sub-type, product_subtype beating sub_type (config.SOT_SUBTYPE_KEYS order)."""
    best = {}
    for r in sot_rows:
        v = _clean(r["value"])
        if not v: continue
        pri = C.SOT_SUBTYPE_KEYS.index(r["key"].strip())
        if r["sku"] not in best or pri < best[r["sku"]][0]: best[r["sku"]] = (pri, v)
    return {k: v for k, (_, v) in best.items()}


def is_lighting(category_path):
    return any(seg.strip().lower() == "lighting" for seg in (category_path or "").split(":"))


def search_term(subtype, category_path):
    """Returns (term, rule_applied)."""
    if not subtype: return None, "no sub-type -> NOT VERIFIED"
    if re.search(r"\bLED\b", subtype, re.I): return subtype, "sub-type already contains LED"
    if not is_lighting(category_path): return subtype, "category outside Lighting -> no LED prefix"
    return f"LED {subtype}", "'LED' + Product Sub-Type (Keyword Analysis.pdf Step 2)"


def map_one(rec, sot):
    out = {"product_id": rec["product_id"], "sku": rec.get("sku"), "sot_subtype": None, "ebay_category": None, "ebay_category_path": rec.get("ebay_category_path"),
           "product_subtype": None, "mapping_source": None, "mapping_status": "NOT VERIFIED", "mapping_note": "", "search_term": None, "search_term_rule": None}
    if not rec["found"]:
        out["mapping_note"] = "Product ID not found in the database"; return out
    subs = Counter(sot[s] for s in rec["listing_skus"] if s in sot)
    path = (rec.get("ebay_category_path") or "").strip()
    leaf = path.split(":")[-1].strip() if path else None
    out["ebay_category"] = leaf or None
    if subs:
        top = sorted(subs.items(), key=lambda kv: (-kv[1], kv[0]))
        out.update(sot_subtype=top[0][0], product_subtype=top[0][0], mapping_source="SOT_SUBTYPE", mapping_status="VERIFIED",
                   mapping_note=f"{top[0][1]} of {len(rec['listing_skus'])} listing SKUs carry this SOT sub-type"
                                + (f"; other SOT sub-types: {[k for k, _ in top[1:]]}" if len(top) > 1 else ""))
    elif leaf:
        out.update(product_subtype=leaf, mapping_source="EBAY_CATEGORY", mapping_status="VERIFIED",
                   mapping_note=f"no SOT sub-type for any of {len(rec['listing_skus'])} listing SKUs; eBay category leaf used")
    else:
        out["mapping_note"] = f"no SOT sub-type for any of {len(rec['listing_skus'])} listing SKUs and no eBay category"
    out["search_term"], out["search_term_rule"] = search_term(out["product_subtype"], path)
    return out


def map_all(snapshot):
    sot = sot_by_sku(snapshot["sot"])
    return [map_one(r, sot) for r in snapshot["records"]]


COLUMNS = ["product_id", "sku", "sot_subtype", "ebay_category", "ebay_category_path", "product_subtype", "mapping_source", "mapping_status", "mapping_note"]
TERM_COLUMNS = ["product_id", "product_subtype", "mapping_source", "ebay_category_path", "search_term_rule", "search_term"]


def write_csv(rows, path, columns=COLUMNS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns); w.writeheader()
        for r in rows: w.writerow({k: r.get(k) for k in columns})
