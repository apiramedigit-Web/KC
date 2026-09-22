"""Stage S6 RESEARCH: eBay UK competitor research per approved Product ID (Keyword Analysis.pdf steps 1-7).

Per Product ID:
  Step 1  UK-VPN Chrome over CDP (config.CDP_URL), own tab only; exit country must be GB (re-checked every N IDs)
  Step 2  search term from map_products (sub-type + LED)
  Step 3  eBay UK, Buy It Now + New + Item Location UK Only, result pages 1-3
  Step 4  internal accounts excluded: seller tokens (Ledsone, Electricalsone, sunsone, ...), every store in
          ebay_campaigns.seller_stores, and any candidate listing ID that is one of our own listings in the DB
  Step 5  screen against THIS listing's own title -> EXACT MATCH / SIMILAR / SAME CATEGORY; shortlist 6
  Step 6  item page + seller description for each shortlisted listing. Last 30 Days Sales: NOT VERIFIED
          (eBay /bin/purchaseHistory needs sign-in behind a CAPTCHA; never bypassed)
  Step 7  final up to 5: tier, item-page 'N sold', eBay order. Eligible = page served, located in UK, not ended,
          item-page seller not internal. >=3 VERIFIED, 2 PARTIAL, <2 NOT_VERIFIED.
CAPTCHA / sign-in page -> Blocked: research stops for this run (never bypassed), the ID is NOT_VERIFIED, retried next run.

Evidence (one capture per search term per day, one per competitor listing per day; each ID names what it used):
  04_research/search_results/<day>/<term_key>.json + _p1..3.html
  04_research/competitor_listings/<day>/<listing_id>.json + item_<listing_id>.html
  04_research/descriptions/<day>/desc_<listing_id>.txt
  04_research/keyword_evidence/<day>/<product_id>.json       (keywords/ranks added by stages S7/S8)
Persistent status: 05_evidence/research_logs/research_status.json (PENDING/IN_PROGRESS/VERIFIED/PARTIAL/NOT_VERIFIED/FAILED)

Reused (copied) from the old project Keywords check/01_Source:
  research_groups.py  parse_page, internal-account test, toks, has_word, goto, check_uk, Blocked, STOP
  research_ids.py     search_capture, item_capture, profile, screen, final selection
Changes: dated evidence folders (no never-expiring cache), status store/resume, own-ID check against the DB
for candidate IDs only, config-driven browser address and limits."""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

import config as C
import logger as L

TIERS = ["EXACT MATCH", "SIMILAR", "SAME CATEGORY"]
STATUSES = ("PENDING", "IN_PROGRESS", "VERIFIED", "PARTIAL", "NOT_VERIFIED", "FAILED")
DONE_FOR_DAY = {"VERIFIED", "PARTIAL"}          # never re-researched the same day
SELLER_RE = re.compile(r"^(?P<name>.+?)\s+\d{1,3}(?:\.\d)?%\s+positive\s+\(")
SOLD_RE = re.compile(r"^([\d,]+\+?)\s+sold$", re.I)
UI = "Opens in a new window or tab"
STOP = {"and", "or", "the", "for", "with", "of", "to", "in", "on", "a", "an", "&", "by", "from", "x", "uk", "new", "led"}
now = lambda: datetime.now(timezone.utc).isoformat()
term_key = lambda s: hashlib.md5(s.lower().encode()).hexdigest()[:12]


class Blocked(Exception):
    """eBay served a CAPTCHA or sign-in page. Never bypassed."""


class ExitNotUK(Exception):
    pass


# ---------------------------------------------------------------- status store
def load_status():
    return json.loads(C.STATUS_FILE.read_text(encoding="utf-8")) if C.STATUS_FILE.exists() else {}


def save_status(st):
    C.write_json_atomic(C.STATUS_FILE, st)


def set_status(st, pid, day, run_id, status, **kw):
    assert status in STATUSES, status
    cur = st.get(pid, {})
    if cur.get("day") != day: cur = {"last_verified": cur.get("last_verified"), "attempts": 0}
    cur.update(day=day, run_id=run_id, status=status, updated_at=now(), **kw)
    if status == "IN_PROGRESS": cur["attempts"] = cur.get("attempts", 0) + 1
    st[pid] = cur
    return cur


def needs_research(st, pid, day):
    """True unless the ID already finished today (VERIFIED/PARTIAL, or NOT_VERIFIED for lack of competitors)."""
    cur = st.get(pid) or {}
    if cur.get("day") != day: return True
    if cur.get("status") in DONE_FOR_DAY: return False
    if cur.get("status") == "NOT_VERIFIED" and not cur.get("retryable"): return False
    return True


# ---------------------------------------------------------------- internal accounts
def sq(v):
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def load_stores(conn):
    rows = conn.execute("select seller_store_name, ebay_seller_store_username from ebay_campaigns.seller_stores").fetchall()
    return {sq(x) for r in rows for x in r if sq(x)}


def own_listing_ids(conn, candidate_ids):
    """Which of these candidate listing IDs are OUR listings (any marketplace/account). Candidate IDs only."""
    if not candidate_ids: return set()
    rows = conn.execute("select distinct item_id from listings.ebay_listings where item_id = any(%s)", (list(candidate_ids),)).fetchall()
    return {r[0].strip() for r in rows}


def internal_seller(seller, stores):
    s = (seller or "").lower()
    return bool(seller) and (any(t in s for t in C.INTERNAL_TOKENS) or sq(seller) in stores)


# ---------------------------------------------------------------- parsing / screening
def toks(s):
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def has_word(tt, w):
    return any(t == w or t == w + "s" or t == w + "es" or (w.endswith("s") and t == w[:-1]) for t in tt)


def parse_page(path, page_no):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    out, pos = [], 0
    for card in soup.select("[data-listingid]"):
        lid = card.get("data-listingid", "")
        node = card.select_one(".s-card__title")
        if not re.fullmatch(r"\d{11,13}", lid) or not node: continue
        title = " ".join(p for p in (s.strip() for s in node.stripped_strings) if p and p != UI and p.lower() != "new listing")
        if not title or title == "Shop on eBay": continue
        pos += 1
        seller = sold = None
        for row in card.select(".s-card__attribute-row"):
            txt = " ".join(row.get_text(" ", strip=True).split())
            m = SELLER_RE.match(txt); seller = seller or (m and m.group("name").strip())
            m = SOLD_RE.match(txt); sold = sold or (m and m.group(1))
        out.append({"listing_id": lid, "card_title": title, "card_seller": seller, "card_sold_text": sold, "result_page": page_no, "result_position": pos})
    return out


def profile(product_subtype, product_name):
    alts = [[w for w in toks(a) if w not in STOP] for a in re.split(r"\s*(?:&|,|\band\b)\s*", (product_subtype or "").replace("/", " ")) if a.strip()]
    alts = [a for a in alts if a]
    heads = [next((w for w in reversed(a) if not re.search(r"\d", w)), a[-1]) for a in alts]
    own = list(dict.fromkeys(w for w in toks(product_name) if w not in STOP and not w.isdigit()))
    return {"alternatives": alts, "heads": heads, "own_title_tokens": own}


def screen(title, prof):
    tt = toks(title); own = prof["own_title_tokens"]
    sim = sum(has_word(tt, w) for w in own) / max(1, len(own))
    full = any(all(has_word(tt, w) for w in a) for a in prof["alternatives"])
    head = any(has_word(tt, h) for h in prof["heads"])
    if full and sim >= 0.4: return "EXACT MATCH", round(sim, 3)
    if full or (head and sim >= 0.4): return "SIMILAR", round(sim, 3)
    if head or sim >= 0.4: return "SAME CATEGORY", round(sim, 3)
    return "NOT RELEVANT", round(sim, 3)


def soldn(text):
    m = re.match(r"[\d,]+", text or ""); return int(m.group().replace(",", "")) if m else 0


# ---------------------------------------------------------------- browser
def goto(pg, url, wait="domcontentloaded"):
    st = None
    for att in range(3):
        try:
            r = pg.goto(url, timeout=60000, wait_until=wait)
            pg.wait_for_timeout(1500)
            if "captcha" in pg.url or "signin." in pg.url: raise Blocked(pg.url)
            if r and r.status == 200: return 200
            st = r.status if r else None
        except Blocked:
            raise
        except Exception as ex:
            st = type(ex).__name__
        time.sleep(4 * (att + 1))
    return st


def check_uk(pg):
    pg.goto(C.EXIT_CHECK_URL, timeout=30000)
    ip = json.loads(re.sub(r"<[^>]+>", "", pg.inner_text("body")))
    if ip.get("country") != C.REQUIRED_EXIT_COUNTRY: raise ExitNotUK(f"exit country {ip.get('country')}")
    return {k: ip.get(k) for k in ("ip", "country", "city", "org")}


def search_capture(pg, term, day, conn, stores):
    d = C.SEARCH_RESULTS / day; d.mkdir(parents=True, exist_ok=True)
    f = d / f"{term_key(term)}.json"
    if f.exists(): return json.loads(f.read_text(encoding="utf-8"))
    rec = {"search_term": term, "term_key": term_key(term), "captured_at": now(), "pages": [], "candidates": []}
    seen = set()
    for n in C.SEARCH_PAGES:
        url = C.SEARCH_URL.format(q=quote_plus(term), p=n); st = goto(pg, url)
        dest = d / f"{term_key(term)}_p{n}.html"
        if st == 200:
            dest.write_text(pg.content(), encoding="utf-8")
            for c in parse_page(dest, n):
                if c["listing_id"] not in seen:
                    seen.add(c["listing_id"]); c["raw_page"] = C.rel(dest); rec["candidates"].append(c)
        rec["pages"].append({"page": n, "url": url, "http_status": st, "raw_html": C.rel(dest) if st == 200 else None})
        time.sleep(C.PAGE_PAUSE_S)
    own = own_listing_ids(conn, [c["listing_id"] for c in rec["candidates"]])
    for c in rec["candidates"]:
        c["internal_reason"] = "our listing ID" if c["listing_id"] in own else ("internal seller" if internal_seller(c["card_seller"], stores) else None)
        c["internal"] = bool(c["internal_reason"])
    rec["complete"] = all(p["http_status"] == 200 for p in rec["pages"])
    if rec["complete"]: f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def item_capture(pg, lid, day, stores):
    d = C.COMPETITOR_LISTINGS / day; d.mkdir(parents=True, exist_ok=True)
    dd = C.DESCRIPTIONS / day; dd.mkdir(parents=True, exist_ok=True)
    f = d / f"{lid}.json"
    if f.exists(): return json.loads(f.read_text(encoding="utf-8"))
    it = {"listing_id": lid, "url": C.ITEM_URL.format(lid=lid), "captured_at": now()}
    st = goto(pg, it["url"], "load"); pg.wait_for_timeout(800); it["http_status"] = st
    if st != 200:
        it["status"] = f"ITEM PAGE NOT SERVED ({st})"; return it
    p = d / f"item_{lid}.html"; p.write_text(pg.content(), encoding="utf-8"); it["raw_item_page"] = C.rel(p)
    q = lambda sel: (pg.locator(sel).first.inner_text(timeout=3000).strip() if pg.locator(sel).count() else None)
    it["item_title"] = q("h1.x-item-title__mainTitle")
    it["seller"] = q(".x-sellercard-atf__info__about-seller a span") or q(".x-sellercard-atf__info__about-seller")
    body = pg.inner_text("body")
    m = re.search(r"([\d,]+)\s+sold", body); it["item_page_sold_text"] = m.group(0) if m else None
    m = re.search(r"Located in:\s*([^\n]+)", body); it["item_location"] = m.group(1).strip() if m else None
    it["ended"] = bool(re.search(r"This listing (was ended|has ended)|no longer available", body, re.I))
    src = pg.locator("#desc_ifr").first.get_attribute("src") if pg.locator("#desc_ifr").count() else None
    if src:
        dpg = pg.context.new_page()
        try:
            for _ in range(2):
                try:
                    dpg.goto(src, timeout=45000, wait_until="domcontentloaded"); dpg.wait_for_timeout(1000)
                    dp = dd / f"desc_{lid}.txt"; dp.write_text(dpg.inner_text("body"), encoding="utf-8"); it["raw_description"] = C.rel(dp); break
                except Exception as ex:
                    it["description_error"] = type(ex).__name__
        finally:
            dpg.close()
    it["internal_by_item_seller"] = internal_seller(it["seller"], stores)
    it["status"] = "OK" if it["item_title"] else "NO TITLE READ"
    f.write_text(json.dumps(it, ensure_ascii=False, indent=1), encoding="utf-8")
    return it


# ---------------------------------------------------------------- per Product ID
def select_final(shortlist):
    elig = [s for s in shortlist if s["item"].get("status") == "OK" and "united kingdom" in (s["item"].get("item_location") or "").lower()
            and not s["item"].get("ended") and not s["item"].get("internal_by_item_seller")]
    return sorted(elig, key=lambda s: (TIERS.index(s["tier"]), -soldn(s["item"].get("item_page_sold_text")), s["result_page"], s["result_position"]))[:C.FINAL_MAX]


def verification(n):
    return "VERIFIED" if n >= C.VERIFIED_MIN else ("PARTIAL" if n >= C.PARTIAL_MIN else "NOT_VERIFIED")


def research_one(pg, src, m, day, run_id, exit_ip, conn, stores):
    """src = snapshot record, m = mapping row. Returns the evidence record (keywords filled later)."""
    ev = {"product_id": src["product_id"], "sku": src.get("sku"), "product_name": src.get("product_name"), "origin": "LIVE",
          "run_id": run_id, "run_date": day, "product_subtype": m["product_subtype"], "mapping_source": m["mapping_source"],
          "search_term": m["search_term"], "search_term_rule": m["search_term_rule"], "exit_ip": exit_ip, "started_at": now()}
    sc = search_capture(pg, m["search_term"], day, conn, stores)
    ev["search_evidence"] = {"search_capture": C.rel(C.SEARCH_RESULTS / day / f"{term_key(m['search_term'])}.json") if sc["complete"] else None,
                             "captured_at": sc["captured_at"], "pages": sc["pages"], "complete": sc["complete"]}
    prof = profile(m["product_subtype"], src.get("product_name")); ev["screening_profile"] = prof
    pool = []
    for c in sc["candidates"]:
        if c["internal"]: continue
        tier, sim = screen(c["card_title"], prof)
        pool.append({**{k: c[k] for k in ("listing_id", "card_title", "card_seller", "card_sold_text", "result_page", "result_position", "raw_page")}, "tier": tier, "similarity": sim})
    ev["candidates"] = len(sc["candidates"]); ev["internal_excluded"] = [c["listing_id"] for c in sc["candidates"] if c["internal"]]
    ev["tier_counts"] = {t: sum(p["tier"] == t for p in pool) for t in TIERS + ["NOT RELEVANT"]}
    ranked = sorted([p for p in pool if p["tier"] in TIERS], key=lambda p: (TIERS.index(p["tier"]), -p["similarity"], p["result_page"], p["result_position"]))
    short = []
    for p in ranked[:C.SHORTLIST]:
        short.append({**p, "item": item_capture(pg, p["listing_id"], day, stores)}); time.sleep(1)
    ev["shortlist"] = [{**{k: s[k] for k in ("listing_id", "tier", "similarity", "result_page", "result_position")},
                        "item_capture": C.rel(C.COMPETITOR_LISTINGS / day / f"{s['listing_id']}.json") if s["item"].get("raw_item_page") else None,
                        "item_status": s["item"].get("status"), "item_location": s["item"].get("item_location"),
                        "internal_by_item_seller": s["item"].get("internal_by_item_seller")} for s in short]
    ev["final_competitors"] = [final_row(s) for s in select_final(short)]
    ev["verification_status"] = verification(len(ev["final_competitors"]))
    ev["research_status"] = "RESEARCHED" if sc["complete"] else "INCOMPLETE SEARCH CAPTURE"
    ev["captured_at"] = sc["captured_at"]; ev["finished_at"] = now()
    return ev


def final_row(s):
    it = s["item"]
    return {"listing_id": s["listing_id"], "seller": it.get("seller") or s["card_seller"] or "NOT VERIFIED", "title": it["item_title"], "url": it["url"],
            "search_page": s["result_page"], "search_position": s["result_position"], "product_match": s["tier"], "similarity": s["similarity"],
            "sold": it.get("item_page_sold_text") or "NOT VERIFIED", "sales_30_day": "NOT VERIFIED",
            "description_checked": "Yes" if it.get("raw_description") else "NOT AVAILABLE", "item_location": it.get("item_location"),
            "captured_at": it.get("captured_at"), "raw_search_page": s["raw_page"], "raw_item_page": it["raw_item_page"],
            "raw_description": it.get("raw_description")}


def evidence_path(day, pid):
    return C.KEYWORD_EVIDENCE / day / f"{pid}.json"


def run(snapshot, mapping, day, run_id, conn, dry_run=False):
    """Research every approved, active, mapped Product ID that has not finished today. Returns per-ID outcome."""
    log = L.get(); st = load_status(); by_map = {m["product_id"]: m for m in mapping}
    todo, skipped = [], {}
    for r in snapshot["records"]:
        pid, m = r["product_id"], by_map[r["product_id"]]
        if not r["found"]: skipped[pid] = "not found in DB"; continue
        if not (r.get("listing_status") == "Active" and not r.get("is_ended")): skipped[pid] = "listing not active"; continue
        if m["mapping_status"] != "VERIFIED" or not m["search_term"]: skipped[pid] = "mapping NOT VERIFIED"; continue
        if not needs_research(st, pid, day): skipped[pid] = f"already {st[pid]['status']} today"; continue
        todo.append((r, m))
    out = {"todo": [r["product_id"] for r, _ in todo], "skipped": skipped, "results": {}, "stopped": None}
    L.event("RESEARCH", "PLAN", todo=len(todo), skipped=len(skipped), detail=skipped)
    if dry_run or not todo:
        out["stopped"] = "dry-run: no browser" if dry_run and todo else None
        return out
    for r, _ in todo:
        if st.get(r["product_id"], {}).get("day") != day or st[r["product_id"]]["status"] not in ("IN_PROGRESS", "FAILED", "NOT_VERIFIED"):
            set_status(st, r["product_id"], day, run_id, "PENDING")
    save_status(st)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as ex:
        return _fail_all(st, todo, day, run_id, out, f"playwright not installed: {ex}")
    stores = load_stores(conn)
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp(C.CDP_URL, timeout=15000)
        except Exception as ex:
            return _fail_all(st, todo, day, run_id, out, f"browser not reachable at {C.CDP_URL}: {type(ex).__name__}")
        pg = b.contexts[0].new_page()
        try:
            return research_loop(pg, todo, day, run_id, conn, stores, st, out)
        finally:
            pg.close()


def research_loop(pg, todo, day, run_id, conn, stores, st, out):
    """The per-ID loop (separate from browser connection so resume behaviour is testable with a fake page)."""
    try:
        exit_ip = check_uk(pg)
    except Exception as ex:
        return _fail_all(st, todo, day, run_id, out, f"UK exit check failed: {type(ex).__name__}: {ex}")
    L.event("RESEARCH", "EXIT_OK", exit=exit_ip)
    for k, (r, m) in enumerate(todo, 1):
        pid = r["product_id"]
        if k > 1 and (k - 1) % C.UK_CHECK_EVERY == 0:
            try: exit_ip = check_uk(pg)
            except Exception as ex:
                _fail_all(st, todo[k - 1:], day, run_id, out, f"UK exit lost: {ex}"); break
        set_status(st, pid, day, run_id, "IN_PROGRESS"); save_status(st)
        try:
            ev = research_one(pg, r, m, day, run_id, exit_ip, conn, stores)
        except Blocked as ex:
            set_status(st, pid, day, run_id, "NOT_VERIFIED", retryable=True, error=f"blocked by eBay (CAPTCHA/sign-in, not bypassed): {ex}")
            save_status(st); out["results"][pid] = "NOT_VERIFIED (blocked)"; out["stopped"] = "blocked"
            L.event("RESEARCH", "BLOCKED", product_id=pid); break
        except Exception as ex:
            set_status(st, pid, day, run_id, "FAILED", retryable=True, error=f"{type(ex).__name__}: {str(ex)[:200]}")
            save_status(st); out["results"][pid] = "FAILED"; L.event("RESEARCH", "FAILED", product_id=pid, error=type(ex).__name__); continue
        path = evidence_path(day, pid); C.write_json_atomic(path, ev)
        status = ev["verification_status"] if ev["research_status"] == "RESEARCHED" else "FAILED"
        extra = {"evidence": C.rel(path), "research_captured_at": ev["captured_at"], "retryable": status == "FAILED", "error": None if status != "FAILED" else "incomplete search capture"}
        cur = set_status(st, pid, day, run_id, status, **extra)
        if status in DONE_FOR_DAY:
            cur["last_verified"] = {"day": day, "evidence": C.rel(path), "captured_at": ev["captured_at"], "origin": "LIVE", "status": status}
        save_status(st); out["results"][pid] = status
        L.event("RESEARCH", status, product_id=pid, term=m["search_term"], final=len(ev["final_competitors"]))
    return out


def _fail_all(st, todo, day, run_id, out, reason):
    for r, _ in todo:
        pid = r["product_id"]
        if pid in out["results"]: continue
        cur = set_status(st, pid, day, run_id, "FAILED", retryable=True, error=reason); out["results"][pid] = "FAILED"
        cur["attempts"] = cur.get("attempts", 0) + 1
    save_status(st); out["stopped"] = reason
    L.event("RESEARCH", "STOPPED", reason=reason)
    return out
