"""Stage S8 CALCULATE RANKS: Keyword Rank for every keyword of one Product ID, independently.

Keyword Rank (requirement CSV: 'How many times Competitors Use in the Title Specific or Des[cription]') =
number of THIS Product ID's verified final competitor listings whose TITLE or DESCRIPTION contains the phrase.
Each listing counts once. It is not an eBay search position, sales figure or estimate.
Match: case-insensitive, whole words, space or hyphen between words, optional plural s/es on the last word.
Description = seller description with store boilerplate removed (clean_description).
No final competitors -> 'NOT VERIFIED' (never 0, never estimated).
Reused (copied) from Keywords check/01_Source/analyze_groups.py: clean_description, matcher, rank logic."""
import re

import config as C

BOILER = re.compile(r"£\s?\d|\d\s*GBP\b|\bGBP\b|\$\s?\d|€\s?\d|buy it now|free shipping|free delivery|may you like|you may also like|shop categories|store categories|"
                    r"powered by|visit (my|our) (ebay )?(store|shop)|add to (favourite|favorite)|sign up|newsletter|contact us|about us|feedback|"
                    r"see our ebay store|all items|payment|paypal|pay securely|returns? policy|shipping policy", re.I)
NOT_VERIFIED = "NOT VERIFIED"


def clean_description(txt):
    lines = [l.strip() for l in (txt or "").splitlines() if l.strip()]
    price = re.compile(r"^(£\s?[\d,.]+|[\d,.]+\s*(GBP|£)|US\s?\$[\d,.]+)$", re.I)
    lines = [l for i, l in enumerate(lines) if not (i + 1 < len(lines) and price.match(lines[i + 1]))]  # cross-sell tiles
    keep, run = [], []

    def flush():
        if len(run) < 4: keep.extend(run)
        run.clear()
    for l in lines:
        if BOILER.search(l): flush(); continue
        if len(l) <= 40 and not re.search(r"[:.!?]", l): run.append(l); continue      # store menu runs
        flush(); keep.append(l)
    flush()
    return "\n".join(keep)


def matcher(k):
    body = r"[\s\-]+".join(map(re.escape, k.split()))
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?:e?s)?(?![A-Za-z0-9])", re.I)


def competitor_texts(ev):
    out = []
    for c in ev.get("final_competitors") or []:
        desc = (C.ROOT / c["raw_description"]).read_text(encoding="utf-8") if c.get("raw_description") else ""
        out.append((c["listing_id"], c["title"] or "", clean_description(desc)))
    return out


def rank(keyword, texts):
    if not texts: return {"keyword": keyword, "keyword_rank": NOT_VERIFIED, "of_competitors": 0, "matches": []}
    lp, m = matcher(keyword), []
    for lid, title, desc in texts:
        where = [w for w, tx in (("title", title), ("description", desc)) if lp.search(tx)]
        if where:
            src = title if "title" in where else desc; mm = lp.search(src)
            m.append({"listing_id": lid, "found_in": where, "snippet": " ".join(src[max(0, mm.start() - 50):mm.end() + 40].split())})
    return {"keyword": keyword, "keyword_rank": len(m), "of_competitors": len(texts), "matches": m}


def ranks_for(ev, keywords):
    texts = competitor_texts(ev)
    return {g: [{**rank(k["keyword"], texts), "titles_with_phrase": k["titles_with_phrase"]} for k in ks] for g, ks in keywords.items()}
