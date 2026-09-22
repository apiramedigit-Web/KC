"""Stage S7 EXTRACT KEYWORDS: keywords for one Product ID from ITS OWN final competitor titles only.

Keyword Analysis.pdf Step 8 ('keywords and phrases that appear across multiple relevant titles'):
contiguous word n-grams (1-5 words) of the final competitor TITLES, never across punctuation, present in >=2 titles
(plural of a word ignored for counting); not starting/ending with a stop word, not numbers only; a phrase is dropped
when a longer phrase containing it occurs in the same number of titles.
Short-tail = 1-2 words, Long-tail = 3+ words (PDF definitions).
  Primary Keyword    : highest-count short-tail phrase containing the product head noun (else highest short-tail)
  Secondary Keywords : next 3 short-tail phrases
  Long-Tail Keywords : top 3 long-tail phrases
  Competitor Keywords: top 3 remaining repeated competitor phrases NOT present in our own listing title
A phrase contained in an already chosen keyword is skipped. Ties: more titles, more words, first occurrence.
Fewer than 2 final competitors -> no keywords (NOT VERIFIED). The requirement CSV's example keywords are never used.
Reused (copied) from Keywords check/01_Source/analyze_groups.py (sing, ngrams, extract, choose) and the
competitor-keyword rule of research_ids.py."""
import re
from collections import Counter, defaultdict

import calculate_ranks as R

STOP = {"and", "or", "the", "for", "with", "of", "to", "in", "on", "a", "an", "by", "from", "x", "at", "as", "is", "your", "our", "&", "+"}
GROUPS = ["Primary Keyword", "Secondary Keywords", "Long-Tail Keywords", "Competitor Keywords"]


def sing(t):
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t


def ngrams(title):
    """(key, surface, position) for every n-gram that does not cross punctuation."""
    out = []
    for seg in re.split(r"[,|;:()\[\]{}!?/+•·–—]|\s-\s", title):
        ws = list(re.finditer(r"[A-Za-z0-9]+(?:['.][A-Za-z0-9]+)*", seg))
        for i in range(len(ws)):
            for n in range(1, 6):
                if i + n > len(ws): break
                part = ws[i:i + n]
                gap = seg[part[0].start():part[-1].end()]
                if re.search(r"[^\sA-Za-z0-9'.\-]", gap): break
                low = [p.group().lower() for p in part]
                if low[0] in STOP or low[-1] in STOP or all(re.fullmatch(r"\d+", x) for x in low): continue
                if n == 1 and (len(low[0]) < 2 or low[0] in STOP): continue
                out.append((tuple(sing(x) for x in low), " ".join(p.group() for p in part), i))
    return out


def contains(big, small):
    return len(big) > len(small) and any(big[i:i + len(small)] == small for i in range(len(big) - len(small) + 1))


def extract(titles):
    df, surf, first = Counter(), defaultdict(Counter), {}
    for ti, t in enumerate(titles):
        seen = set()
        for key, s, pos in ngrams(t):
            surf[key][s] += 1
            first.setdefault(key, (ti, pos))
            if key not in seen: seen.add(key); df[key] += 1
    keys = [k for k, v in df.items() if v >= 2]
    keys = [k for k in keys if not any(contains(o, k) and df[o] == df[k] for o in keys)]
    pool = sorted(keys, key=lambda k: (-df[k], -len(k), first[k]))
    disp = {k: surf[k].most_common(1)[0][0] for k in pool}
    return pool, df, disp


def choose(pool, heads):
    short = [k for k in pool if len(k) <= 2]
    longt = [k for k in pool if len(k) >= 3]
    hs = {sing(h) for h in heads}
    prim = next((k for k in short if hs & set(k)), short[0] if short else None)
    chosen = [prim] if prim else []
    covered = lambda k: any(k == c or contains(c, k) for c in chosen)
    sec, lt = [], []
    for k in short:
        if len(sec) == 3: break
        if not covered(k): sec.append(k); chosen.append(k)
    for k in longt:
        if len(lt) == 3: break
        if not covered(k): lt.append(k); chosen.append(k)
    rest = [k for k in pool if not covered(k)]
    return prim, sec, lt, rest


def keywords_for(ev):
    """Returns {group: [{"keyword", "titles_with_phrase"}]} or {} when fewer than 2 final competitors."""
    comps = ev.get("final_competitors") or []
    if len(comps) < 2: return {}
    pool, df, disp = extract([c["title"] for c in comps])
    prim, sec, lt, rest = choose(pool, ev["screening_profile"]["heads"])
    own = ev.get("product_name") or ""
    comp_k = []
    for k in rest:
        if len(comp_k) == 3: break
        if R.matcher(disp[k]).search(own): continue
        if any(k == c or contains(c, k) or contains(k, c) for c in comp_k): continue
        comp_k.append(k)
    item = lambda k: {"keyword": disp[k], "titles_with_phrase": df[k]}
    return {"Primary Keyword": [item(prim)] if prim else [], "Secondary Keywords": [item(k) for k in sec],
            "Long-Tail Keywords": [item(k) for k in lt], "Competitor Keywords": [item(k) for k in comp_k]}
