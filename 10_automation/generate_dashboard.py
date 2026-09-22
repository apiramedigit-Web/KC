"""Stage S9 BUILD DASHBOARD: run dataset + standalone HTML (07_report/.staging/, never the live file).

Rows = exactly the approved Product IDs, in scope.json order. Main table = the requirement CSV's 11 columns, read
from the CSV at build time. Each row carries freshness: CURRENT (researched in this run's day), CARRIED FORWARD
from <date> (today's research failed; last verified evidence shown with its own date), NOT VERIFIED, LISTING ENDED.
Everything is embedded (CSS, JS, data); the only links are outbound eBay / Document links. Never hand-edit the HTML.
Layout reused from Keywords check/01_Source/build_report_requested.py."""
import csv
import html
import json
from datetime import datetime, timezone

import config as C
import extract_keywords as K
import research

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def requirement():
    rows = list(csv.reader(open(C.REQUIREMENT_CSV, encoding="utf-8-sig")))
    cols = [rows[1][0], rows[1][1], rows[1][2]] + rows[2][3:11]
    doc = next(r[1] for r in rows if r[0].strip().lower().startswith("docun"))
    rdef = next(" ".join(x for x in r[1:] if x) for r in rows if r[0].strip() == "Rank")
    return {"columns": cols, "group_header": rows[1][3], "document_url": doc, "rank_definition": rdef}


def _load(rel_path):
    p = C.ROOT / rel_path
    return json.loads(p.read_text(encoding="utf-8")) if rel_path and p.exists() else None


def pick_evidence(pid, day, st):
    """(evidence, freshness_label, today_status) for one Product ID."""
    cur = st.get(pid) or {}
    today = cur if cur.get("day") == day else {}
    if today.get("status") in ("VERIFIED", "PARTIAL") or (today.get("status") == "NOT_VERIFIED" and not today.get("retryable")):
        ev = _load(today.get("evidence"))
        if ev and ev.get("origin") == "LIVE" and ev.get("run_date") == day: return ev, "CURRENT", today
    lv = cur.get("last_verified")
    if lv:
        ev = _load(lv["evidence"])
        if ev: return ev, f"CARRIED FORWARD from {lv['day']}" + (" (imported from old project)" if lv.get("origin") == "IMPORTED" else ""), today
    return None, "NOT VERIFIED", today


def build_dataset(snap, mapping, day, run_id, changes):
    st = research.load_status(); by_map = {m["product_id"]: m for m in mapping}; rows = []
    for r in snap["records"]:
        pid, m = r["product_id"], by_map[r["product_id"]]
        ev, fresh, today = pick_evidence(pid, day, st)
        active = r.get("found") and r.get("listing_status") == "Active" and not r.get("is_ended")
        if r.get("found") and not active: fresh = "LISTING ENDED" + (f" (last evidence {ev['run_date']})" if ev else "")
        comps = (ev or {}).get("final_competitors") or []
        kw = (ev or {}).get("keywords") or {}
        ver = (ev or {}).get("verification_status") or "NOT_VERIFIED"
        if not ev: ver = "NOT_VERIFIED"
        lv = (st.get(pid) or {}).get("last_verified") or {}
        rows.append({
            "product_id": pid, "sku": r.get("sku"), "product_name": r.get("product_name"), "marketplace": r.get("marketplace"),
            "account": r.get("account"), "listing_status": r.get("listing_status"), "is_ended": r.get("is_ended"),
            "variation_skus": r.get("variation_skus", []), "ebay_category": m.get("ebay_category"), "product_subtype": m.get("product_subtype"),
            "mapping_source": m.get("mapping_source"), "mapping_status": m.get("mapping_status"), "search_term": m.get("search_term"),
            "evidence_search_term": (ev or {}).get("search_term"), "evidence_origin": (ev or {}).get("origin"), "evidence_run_date": (ev or {}).get("run_date"),
            "evidence_file": C.rel(C.ROOT / today["evidence"]) if fresh == "CURRENT" else (lv.get("evidence") if ev else None),
            "verification_status": ver, "freshness": fresh, "change": (changes or {}).get(pid, {}),
            "source_updated_at": str(r.get("source_updated_at")) if r.get("source_updated_at") else "NOT AVAILABLE",
            "research_captured_at": (ev or {}).get("captured_at"), "last_successful_refresh": lv.get("day"),
            "today_research_status": today.get("status") or "NOT RUN", "today_research_error": today.get("error"),
            "keywords": {g: kw.get(g, []) for g in K.GROUPS}, "final_competitors": comps})
    return {"_meta": {"run_id": run_id, "run_date": day, "built_at": datetime.now(timezone.utc).isoformat(), "db_fetched_at": snap["_meta"]["fetched_at"],
                      "scope_version": snap["_meta"]["scope_version"], "approved_ids": snap["_meta"]["approved_ids"], "requirement": requirement()},
            "rows": rows}


def _kcells(row):
    out = ""
    for g in K.GROUPS:
        ks = row["keywords"].get(g) or []
        if not ks:
            why = "no verified competitor evidence" if not row["final_competitors"] else "fewer than 2 competitors share a phrase for this group"
            out += f'<td class="kwc"><div class="kw nv" title="{e(why)}">NOT VERIFIED</div></td><td class="rkc"><div class="rk nv" title="{e(why)}">NOT VERIFIED</div></td>'
            continue
        out += '<td class="kwc">' + "".join(f'<div class="kw">{e(k["keyword"])}</div>' for k in ks) + '</td><td class="rkc">' + "".join(
            f'<div class="rk" title="{e("; ".join(m["listing_id"] + " (" + "+".join(m["found_in"]) + ")" for m in k["matches"]) or "no final competitor uses it")}">{e(k["keyword_rank"])}</div>'
            for k in ks) + "</td>"
    return out


def render(ds):
    M, req = ds["_meta"], ds["_meta"]["requirement"]
    fcls = lambda f: "ok" if f == "CURRENT" else ("nv" if f.startswith(("NOT", "LISTING")) else "cf")
    main, ev, kev = [], [], []
    for r in ds["rows"]:
        vs = f'<div class="sub">Variation SKUs: {e(", ".join(r["variation_skus"]))}</div>' if r["variation_skus"] else ""
        term_note = "" if not r["evidence_search_term"] or r["evidence_search_term"] == r["search_term"] else f' · evidence searched as “{e(r["evidence_search_term"])}”'
        main.append(
            f'<tr data-pid="{e(r["product_id"])}" data-st="{e(r["verification_status"])}" data-fr="{e(r["freshness"].split(" (")[0].split(" from")[0])}" data-site="{e(r["marketplace"])}" data-acct="{e(r["account"])}">'
            f'<td><div class="v">{e(r["sku"])}</div>{vs}</td>'
            f'<td><div class="v"><a href="https://www.ebay.co.uk/itm/{e(r["product_id"])}" target="_blank" rel="noopener">{e(r["product_id"])}</a></div></td>'
            f'<td class="pn"><div class="v">{e(r["product_name"])}</div><div class="sub">{e(r["marketplace"])} · {e(r["account"])} · {e(r["listing_status"])} · '
            f'Sub-type: {e(r["product_subtype"])} ({e(r["mapping_source"] or "NOT VERIFIED")}) · Search term: {e(r["search_term"] or "NOT VERIFIED")}{term_note}<br>'
            f'<span class="{"ok" if r["verification_status"] == "VERIFIED" else "nv"}">{e(r["verification_status"].replace("_", " "))}</span> · '
            f'<span class="{fcls(r["freshness"])}">{e(r["freshness"])}</span> · research captured {e((r["research_captured_at"] or "—")[:16].replace("T", " "))} · '
            f'source updated {e(r["source_updated_at"][:16])}</div></td>' + _kcells(r) + "</tr>")
        for i, c in enumerate(r["final_competitors"], 1):
            ev.append(f'<tr><td>{e(r["product_id"])}</td><td>{e(r["evidence_search_term"])}</td><td>{i}</td><td><a href="{e(c["url"])}" target="_blank" rel="noopener">{e(c["listing_id"])}</a></td>'
                      f'<td>{e(c["seller"])}</td><td class="t">{e(c["title"])}</td><td>{e(c["search_page"])}</td><td>{e(c["search_position"])}</td><td>{e(c["product_match"])}</td>'
                      f'<td>{e(c["sold"])}</td><td class="nv">{e(c["sales_30_day"])}</td><td>{e(c["description_checked"])}</td><td>{e(c["item_location"])}</td>'
                      f'<td>{e((c.get("captured_at") or "")[:16].replace("T", " "))}</td><td class="{fcls(r["freshness"])}">{e(r["freshness"])}</td></tr>')
        for g in K.GROUPS:
            for k in r["keywords"].get(g) or []:
                kev.append(f'<tr><td>{e(r["product_id"])}</td><td>{e(g)}</td><td><b>{e(k["keyword"])}</b></td><td class="rkc">{e(k["keyword_rank"])} / {e(k["of_competitors"])}</td><td>'
                           + "<br>".join(f'{e(m["listing_id"])} · {e("+".join(m["found_in"]))} · “…{e(m["snippet"])}…”' for m in k["matches"]) + "</td></tr>")
    n = len(ds["rows"]); cnt = lambda f: sum(r["freshness"].startswith(f) for r in ds["rows"])
    nver = sum(r["verification_status"] == "VERIFIED" for r in ds["rows"])
    cols = req["columns"]
    head2 = "".join(f"<th>{e(c)}</th>" for c in cols[3:])
    data = json.dumps(ds, ensure_ascii=False, default=str).replace("</", "<\\/")
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Keyword Check – Kobiga</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--mut:#5f6368;--bd:#d9dce1;--hd:#f3f5f8;--acc:#1a56db;--nv:#b42318;--ok:#067647;--cf:#b54708}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#16181c;--fg:#e8eaed;--mut:#a0a6ad;--bd:#343a42;--hd:#20242a;--acc:#7aa7ff;--nv:#ff8a80;--ok:#6ce9a6;--cf:#fdb022}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:1900px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:17px;margin:30px 0 8px}}.mut{{color:var(--mut)}}a{{color:var(--acc)}}
.tw{{overflow-x:auto;border:1px solid var(--bd);border-radius:6px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid var(--bd);padding:6px 8px;vertical-align:top;text-align:left;font-size:13px}}
thead th{{background:var(--hd);font-weight:600;white-space:nowrap}}th.grp{{text-align:center}}
.kw,.rk{{min-height:22px;padding:1px 0;white-space:nowrap}}.kw+.kw,.rk+.rk{{border-top:1px dashed var(--bd)}}.rkc{{text-align:center;font-weight:600;white-space:nowrap}}.rk{{cursor:help}}
.nv{{color:var(--nv);font-weight:600}}.ok{{color:var(--ok);font-weight:600}}.cf{{color:var(--cf);font-weight:600}}.pn{{min-width:300px}}td.t{{min-width:300px}}.sub{{color:var(--mut);font-size:12px;margin-top:3px}}
.note{{background:var(--hd);border:1px solid var(--bd);border-radius:6px;padding:10px 12px;margin:12px 0}}
.flt{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}}.flt input,.flt select{{font:inherit;padding:5px 8px;border:1px solid var(--bd);border-radius:6px;background:var(--bg);color:var(--fg)}}.flt input{{min-width:260px;max-width:100%}}
</style></head><body><main>
<h1>Keyword Check – Kobiga</h1>
<p class="mut">{n} approved Product IDs (scope v{e(M["scope_version"])}) · {nver} VERIFIED · {cnt("CURRENT")} researched today · {cnt("CARRIED")} carried forward · {cnt("NOT")} not verified ·
run {e(M["run_id"])} for {e(M["run_date"])} · database read {e(M["db_fetched_at"][:16].replace("T", " "))} UTC · built {e(M["built_at"][:16].replace("T", " "))} UTC</p>
<div class="note"><b>Keyword Rank</b> (requirement): “{e(req["rank_definition"])}”. Here it is how many of that Product ID’s own verified final competitors (3–5) use the keyword in their title or description. It is not a search position or a sales figure. Hover a Rank to see the listings.
<br><b>Freshness:</b> <span class="ok">CURRENT</span> = researched on eBay UK for this run’s date; <span class="cf">CARRIED FORWARD from date</span> = today’s research did not complete, so the last verified evidence is shown with its own capture date; <span class="nv">NOT VERIFIED</span> = no verified evidence.</div>
<div class="flt"><input id="q" type="search" placeholder="Search SKU, Product ID, name or keyword"><select id="fv"><option value="">Any verification</option><option>VERIFIED</option><option>PARTIAL</option><option>NOT_VERIFIED</option></select>
<select id="ff"><option value="">Any freshness</option><option>CURRENT</option><option>CARRIED FORWARD</option><option>NOT VERIFIED</option><option>LISTING ENDED</option></select><span id="cnt" class="mut"></span></div>
<div class="tw"><table id="kc"><thead><tr><th rowspan="2">{e(cols[0])}</th><th rowspan="2">{e(cols[1])}</th><th rowspan="2">{e(cols[2])}</th><th colspan="8" class="grp">{e(req["group_header"])}</th></tr>
<tr>{head2}</tr></thead><tbody>{"".join(main)}</tbody></table></div>
<p><b>Document:</b> <a href="{e(req["document_url"])}" target="_blank" rel="noopener">{e(req["document_url"])}</a></p>
<h2>How it was done (Keyword Analysis.pdf)</h2><ul class="mut">
<li>Scope: only the approved Product IDs in <code>10_automation/scope.json</code>; the database is queried for those IDs only, every day.</li>
<li>Product/Sub-Type: SOT sub-type when it exists, otherwise the listing’s eBay category (Mapping Source shown per row). Search term = “LED” + sub-type for lighting.</li>
<li>eBay UK through a UK exit, Buy It Now · New · Item Location UK Only, result pages 1–3; listings of our own accounts (Ledsone, Electricalsone, sunsone and all our stores) and our own item IDs excluded.</li>
<li>Screened against each listing’s own title (exact match → similar → same category); 6 shortlisted with item pages checked; final 3–5 by product match and items sold.</li>
<li>Keywords = phrases repeated across that Product ID’s final competitor titles (short-tail 1–2 words, long-tail 3+). Competitor Keywords = repeated competitor phrases missing from our own title.</li>
<li>Last 30 Days Sales: <span class="nv">NOT VERIFIED</span>. eBay’s purchase-history page needs sign-in behind a CAPTCHA, which is never bypassed.</li></ul>
<h2>Competitor evidence</h2><div class="tw"><table id="ce"><thead><tr><th>Product ID</th><th>Search Term</th><th>#</th><th>Listing ID</th><th>Seller</th><th>Listing Title</th><th>Search Page</th><th>Position</th><th>Product Match</th><th>Sold</th><th>Last 30 Days Sales</th><th>Description Checked</th><th>Item Location</th><th>Captured (UTC)</th><th>Freshness</th></tr></thead><tbody>{"".join(ev)}</tbody></table></div>
<h2>Keyword Rank evidence</h2><div class="tw"><table id="ke"><thead><tr><th>Product ID</th><th>Keyword Type</th><th>Keyword</th><th>Keyword Rank</th><th>Competitor listings using it (where · text)</th></tr></thead><tbody>{"".join(kev)}</tbody></table></div>
</main><script type="application/json" id="kc-data">{data}</script><script>
(function(){{var q=document.getElementById('q'),fv=document.getElementById('fv'),ff=document.getElementById('ff'),cnt=document.getElementById('cnt');
var rows=[].slice.call(document.querySelectorAll('#kc tbody tr'));
function apply(){{var t=q.value.trim().toLowerCase(),n=0;rows.forEach(function(r){{var ok=(!t||r.textContent.toLowerCase().indexOf(t)>=0)&&(!fv.value||r.dataset.st===fv.value)&&(!ff.value||r.dataset.fr===ff.value);r.style.display=ok?'':'none';if(ok)n++;}});cnt.textContent=n+' of '+rows.length+' rows';}}
[q,fv,ff].forEach(function(el){{el.addEventListener('input',apply);el.addEventListener('change',apply);}});apply();
document.getElementById('kc').addEventListener('click',function(ev){{var r=ev.target.closest('.rk[title]');if(r)alert(r.title);}});}})();
</script></body></html>"""


def build(ds, run_id):
    C.STAGING.mkdir(parents=True, exist_ok=True)
    path = C.STAGING / f"keyword_check_kobiga.{run_id}.html"
    path.write_text(render(ds), encoding="utf-8")
    return path
