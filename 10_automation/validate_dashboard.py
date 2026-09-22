"""Stage S10 VALIDATE OUTPUT: independent validation of a staged dashboard before any publish.

Independence: Product rows are compared with a FRESH read-only DB query written here (not the fetch SQL, not the
snapshot); every Keyword Rank is recounted from the RAW item-page HTML + raw description files with a token-sequence
matcher (different code from the builder's regex); competitor traceability is checked against the raw search pages.
A FAIL on any critical check blocks local and PH publishing. Result: 06_validation/<date>/local_validation_<run_id>.json.
Checks reused/extended from Keywords check/01_Source/validate_requested.py."""
import hashlib
import html as H
import json
import re

import calculate_ranks  # clean_description only (documented description rule)
import config as C
import extract_keywords as K
import fetch_data
import research

tok = lambda s: re.findall(r"[a-z0-9]+", (s or "").lower())


def uses(text, kw):
    tt, kk = tok(text), tok(kw)
    if not kk: return False
    return any(tt[i:i + len(kk) - 1] == kk[:-1] and tt[i + len(kk) - 1] in (kk[-1], kk[-1] + "s", kk[-1] + "es") for i in range(len(tt) - len(kk) + 1))


def in_title(title, kw):
    """Plural-insensitive whole-phrase test (extraction counts 'Light'/'Lights' as the same phrase)."""
    sg = lambda t: t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t
    tt, kk = [sg(t) for t in tok(title)], [sg(t) for t in tok(kw)]
    return bool(kk) and any(tt[i:i + len(kk)] == kk for i in range(len(tt) - len(kk) + 1))


def raw_title(path):
    m = re.search(r'<h1[^>]*x-item-title__mainTitle[^>]*>(.*?)</h1>', (C.ROOT / path).read_text(encoding="utf-8"), re.S)
    if not m: return ""
    inner = re.sub(r"<wbr\s*/?>", "", m.group(1), flags=re.I)          # eBay line-break hints split words; they are not spaces
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", inner)).split())


def db_rows(ids):
    with fetch_data.connect() as c:
        rows = c.execute("""select trim(e.item_id), trim(e.sku), trim(e.title), trim(e.site), trim(s.seller_store_name)
                            from listings.ebay_listings e left join ebay_campaigns.seller_stores s on s.sub_source = e.sub_source
                            where e.item_id = any(%s) and e.is_parent = 1""", (list(ids),)).fetchall()
        stores = research.load_stores(c)
    return {r[0]: r[1:] for r in rows}, stores


def own_ids(ids):
    with fetch_data.connect() as c:
        return research.own_listing_ids(c, ids)


def parse_main(page):
    tbl = page.split('id="kc"')[1].split("</table>")[0]
    thead = tbl.split("</thead>")[0]
    th = [H.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<th(?![^>]*colspan)[^>]*>(.*?)</th>", thead)]
    group = re.search(r'<th colspan="(\d+)" class="grp">(.*?)</th>', thead)
    body = tbl.split("<tbody>")[1].split("</tbody>")[0]
    first = lambda cell: H.unescape(re.sub(r"<[^>]+>", "", re.search(r'<div class="v">(.*?)</div>', cell, re.S).group(1))).strip()
    rows = []
    for attrs, inner in re.findall(r"<tr ([^>]*)>(.*?)</tr>", body, re.S):
        a = dict(re.findall(r'data-(\w+)="([^"]*)"', attrs))
        tds = re.findall(r"<td[^>]*>(.*?)</td>", inner, re.S)
        kw = re.findall(r'<td class="kwc">(.*?)</td><td class="rkc">(.*?)</td>', inner, re.S)
        rows.append({"attrs": {k: H.unescape(v) for k, v in a.items()}, "sku": first(tds[0]), "pid": first(tds[1]), "name": first(tds[2]),
                     "kw": [([H.unescape(x) for x in re.findall(r'<div class="kw[^"]*"[^>]*>(.*?)</div>', kc)],
                             [H.unescape(x) for x in re.findall(r'<div class="rk[^"]*"[^>]*>(.*?)</div>', rc)]) for kc, rc in kw]})
    return th, group, rows


def validate(html_path, scope, run_date, run_id, browser=True, db=True):
    page = html_path.read_text(encoding="utf-8")
    checks = []
    ck = lambda n, ok, crit=True, d="": checks.append({"check": n, "result": "PASS" if ok else "FAIL", "critical": crit, "detail": d if ok else str(d)[:800]})
    ds = json.loads(re.search(r'<script type="application/json" id="kc-data">(.*?)</script>', page, re.S).group(1))  # "<\/" is valid JSON for "</"
    import generate_dashboard  # requirement() re-read from the CSV, not from the embedded data
    csv_req = generate_dashboard.requirement()
    th, group, rows = parse_main(page)
    ids = scope["product_ids"]

    # --- HTML structure vs requirement CSV
    ck("Column headers == requirement CSV columns, in order", th == csv_req["columns"], d={"html": th, "csv": csv_req["columns"]})
    ck(f"'{csv_req['group_header']}' group header spans the 8 keyword columns", bool(group) and group.group(1) == "8" and H.unescape(group.group(2)) == csv_req["group_header"])
    # --- scope
    pids = [r["pid"] for r in rows]
    ck("Dashboard Product IDs == scope.json IDs (none missing, none extra, same order)", pids == ids, d={"missing": [i for i in ids if i not in pids], "extra": [i for i in pids if i not in ids]})
    ck("No duplicate Product ID rows", len(pids) == len(set(pids)))
    ck("Embedded dataset rows == scope.json IDs", [r["product_id"] for r in ds["rows"]] == ids)
    by = {r["product_id"]: r for r in ds["rows"]}
    # --- data vs fresh DB
    if db:
        dbr, stores = db_rows(ids)
        bad = [p["pid"] for p in rows if p["pid"] not in dbr or (p["sku"], p["name"]) != (dbr[p["pid"]][0] or "", dbr[p["pid"]][1] or "")
               or (by[p["pid"]]["marketplace"], by[p["pid"]]["account"]) != (dbr[p["pid"]][2], dbr[p["pid"]][3])]
        ck("SKU / Product Name / marketplace / account equal a fresh DB read for every row", not bad, d=bad)
    else:
        stores = set()
    ck("Every row has Mapping Source (SOT_SUBTYPE / EBAY_CATEGORY) or Mapping Status NOT VERIFIED",
       all(r["mapping_source"] in ("SOT_SUBTYPE", "EBAY_CATEGORY") or r["mapping_status"] == "NOT VERIFIED" for r in ds["rows"]))
    ck("Every row has a freshness label", all(r["freshness"] and r["attrs"].get("fr") in ("CURRENT", "CARRIED FORWARD", "NOT VERIFIED", "LISTING ENDED") for r in [dict(p, freshness=by[p["pid"]]["freshness"]) for p in rows]))
    stale_current = [r["product_id"] for r in ds["rows"] if r["freshness"] == "CURRENT" and not (r["evidence_origin"] == "LIVE" and r["evidence_run_date"] == run_date)]
    ck("No row labelled CURRENT unless its evidence is LIVE research from this run date", not stale_current, d=stale_current)

    # --- competitor + rank checks from raw evidence
    trace, intern, notuk, capture, ncomp, mism, titles_bad, kw_bad, rank_nv = [], [], [], [], [], [], [], [], []
    all_comp_ids = {c["listing_id"] for r in ds["rows"] for c in r["final_competitors"]}
    ours = own_ids(all_comp_ids) if db and all_comp_ids else set()
    for p in rows:
        r = by[p["pid"]]; comps = r["final_competitors"]
        ev = json.loads((C.ROOT / r["evidence_file"]).read_text(encoding="utf-8")) if r.get("evidence_file") else None
        if comps and not ev: trace.append((p["pid"], "evidence file missing")); continue
        if ev:
            if [c["listing_id"] for c in ev["final_competitors"]] != [c["listing_id"] for c in comps]: trace.append((p["pid"], "dataset competitors differ from evidence file"))
            if ev["product_id"] != p["pid"]: trace.append((p["pid"], "evidence belongs to another Product ID"))
            pages = ev["search_evidence"]["pages"]
            if not ((ev.get("exit_ip") or {}).get("country") == C.REQUIRED_EXIT_COUNTRY and len(pages) == len(C.SEARCH_PAGES)
                    and all(all(f in pg["url"] for f in C.SEARCH_FILTERS) and pg["http_status"] == 200 for pg in pages)): capture.append(p["pid"])
            raw = "".join((C.ROOT / pg["raw_html"]).read_text(encoding="utf-8") for pg in pages if pg.get("raw_html"))
        texts = []
        for c in comps:
            t = raw_title(c["raw_item_page"])
            if t != " ".join((c["title"] or "").split()): titles_bad.append((p["pid"], c["listing_id"]))
            d = calculate_ranks.clean_description((C.ROOT / c["raw_description"]).read_text(encoding="utf-8")) if c.get("raw_description") else ""
            texts.append((t, d))
            if f'data-listingid="{c["listing_id"]}"' not in raw: trace.append((p["pid"], c["listing_id"]))
            if research.internal_seller(c["seller"], stores) or c["listing_id"] in ours: intern.append((p["pid"], c["listing_id"]))
            if "united kingdom" not in (c["item_location"] or "").lower(): notuk.append((p["pid"], c["listing_id"]))
        n = len(comps); exp = research.verification(n) if ev else "NOT_VERIFIED"
        if r["verification_status"] != exp or p["attrs"].get("st") != exp: ncomp.append((p["pid"], n, r["verification_status"]))
        for g, (ks, rs) in zip(K.GROUPS, p["kw"]):
            want = [k["keyword"] for k in r["keywords"].get(g) or []]
            if want and ks != want: mism.append(f"{p['pid']}/{g}: html {ks} vs data {want}")
            if len(ks) != len(rs): mism.append(f"{p['pid']}/{g}: {len(ks)} keywords but {len(rs)} ranks")
            for k, rv in zip(ks, rs):
                if rv == "NOT VERIFIED": continue
                if n < 2: rank_nv.append((p["pid"], k)); continue
                cnt = sum(uses(t, k) or uses(d, k) for t, d in texts)
                if str(cnt) != rv: mism.append(f"{p['pid']}/{g}/{k}: html={rv} recount={cnt}")
                if sum(in_title(t, k) for t, _ in texts) < 2: kw_bad.append((p["pid"], k, "in <2 final titles"))
                if g == "Competitor Keywords" and uses(p["name"], k): kw_bad.append((p["pid"], k, "in our own title"))
    ck("Every competitor belongs to its Product ID's evidence and appears in that ID's captured search pages", not trace, d=trace)
    ck("No internal account / own listing among competitors", not intern, d=intern)
    ck("Search captures: GB exit, Buy It Now + New + UK Only, pages 1-3 served", not capture, d=capture)
    ck("Every competitor item located in the United Kingdom", not notuk, d=notuk)
    ck("Verification status matches competitor count (VERIFIED 3-5, PARTIAL 2, else NOT VERIFIED)", not ncomp, d=ncomp)
    ck("Competitor titles equal the raw item pages", not titles_bad, d=titles_bad)
    ck("Every Keyword Rank equals an independent recount over raw titles + descriptions", not mism, d=mism)
    ck("Every keyword is in >=2 of that ID's final titles; Competitor Keywords not in our own title", not kw_bad, d=kw_bad)
    ck("No numeric Rank where fewer than 2 competitors", not rank_nv, d=rank_nv)
    # --- standalone
    ext = re.findall(r'<script[^>]+src=|<link[^>]+rel="?stylesheet|@import|url\(\s*["\']?https?:|<img[^>]+src=|<iframe', page, re.I)
    ck("Standalone: no external script / stylesheet / font / image / iframe", not ext, d=ext)
    ck("CSS, JavaScript and data embedded", "<style>" in page and "<script>" in page and 'id="kc-data"' in page)
    ck("Rank definition and Document URL from the requirement present", H.escape(csv_req["rank_definition"]) in page and csv_req["document_url"] in page, crit=False)
    # --- browser
    if browser:
        try:
            from playwright.sync_api import sync_playwright
            errs, reqs = [], []
            with sync_playwright() as pw:
                b = pw.chromium.launch(channel="chrome", headless=True); pg = b.new_page(viewport={"width": 1600, "height": 1000})
                pg.on("pageerror", lambda x: errs.append(str(x))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
                pg.on("request", lambda r: not r.url.startswith(("file:", "data:")) and reqs.append(r.url))
                pg.goto(html_path.resolve().as_uri()); pg.wait_for_timeout(500)
                total = pg.locator("#kc tbody tr").count(); vis = lambda: pg.locator("#kc tbody tr:visible").count()
                pg.fill("#q", ids[0]); f_id = vis(); pg.fill("#q", "")
                pg.select_option("#fv", "VERIFIED"); f_v = vis(); pg.select_option("#fv", "")
                pg.select_option("#ff", "CURRENT"); f_c = vis(); pg.select_option("#ff", "")
                back = vis()
                shot = C.SCREENSHOTS / run_date; shot.mkdir(parents=True, exist_ok=True)
                pg.screenshot(path=str(shot / f"dashboard_{run_id}.png"), full_page=False); b.close()
            exp_v = sum(r["verification_status"] == "VERIFIED" for r in ds["rows"]); exp_c = sum(r["freshness"] == "CURRENT" for r in ds["rows"])
            ck("Opens from file:// with no JavaScript errors and no network requests; rendered rows = scope", not errs and not reqs and total == len(ids), d=(errs, reqs, total))
            ck("Search box and filters work (ID search, verification, freshness)", f_id == 1 and f_v == exp_v and f_c == exp_c and back == len(ids), d=(f_id, f_v, exp_v, f_c, exp_c, back))
        except Exception as ex:
            ck("Browser test (headless Chrome)", False, d=f"{type(ex).__name__}: {ex}")
    carried = [r["product_id"] for r in ds["rows"] if r["freshness"] != "CURRENT"]
    ck("All rows researched today (CURRENT)", not carried, crit=False, d=carried)
    crit = [c for c in checks if c["critical"] and c["result"] == "FAIL"]
    return {"run_id": run_id, "run_date": run_date, "html": C.rel(html_path), "html_md5": hashlib.md5(html_path.read_bytes()).hexdigest(),  # bytes on disk
            "overall": "FAIL" if crit else "PASS", "critical_failures": len(crit), "warnings": sum(1 for c in checks if not c["critical"] and c["result"] == "FAIL"),
            "rows": len(rows), "checks": checks}
