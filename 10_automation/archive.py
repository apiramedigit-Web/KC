"""Stage S13 ARCHIVE: one immutable package per run under 11_archive/YYYY/MM/DD/<run_id>/.

Contents: scope.json copy, source snapshot, mapping + search-term CSVs, dataset.json (exactly what the HTML embeds),
the validated dashboard.html, local validation result, PH publish result, run_summary.json, and manifest.json
(path + md5 of every evidence file the dataset references). Raw captures are referenced by path, not copied again."""
import hashlib
import json
import shutil

import config as C

md5 = lambda p: hashlib.md5(p.read_bytes()).hexdigest()


def referenced_files(ds):
    out = set()
    for r in ds["rows"]:
        if r.get("evidence_file"): out.add(r["evidence_file"])
        for c in r["final_competitors"]:
            for k in ("raw_search_page", "raw_item_page", "raw_description"):
                if c.get(k): out.add(c[k])
    for r in ds["rows"]:
        if r.get("evidence_file") and (C.ROOT / r["evidence_file"]).exists():
            ev = json.loads((C.ROOT / r["evidence_file"]).read_text(encoding="utf-8"))
            for p in ev.get("search_evidence", {}).get("pages", []):
                if p.get("raw_html"): out.add(p["raw_html"])
    return sorted(out)


def archive(run_date, run_id, files, dataset, extra):
    """files: {name_in_archive: source_path}; extra: {name: json-able}. Returns archive folder (relative)."""
    y, m, d = run_date.split("-")
    dest = C.ARCHIVE / y / m / d / run_id
    dest.mkdir(parents=True, exist_ok=False)
    for name, src in files.items():
        if src and src.exists(): shutil.copyfile(src, dest / name)
    (dest / "dataset.json").write_text(json.dumps(dataset, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for name, obj in extra.items():
        (dest / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    man = {"run_id": run_id, "run_date": run_date,
           "archived": {p.name: md5(p) for p in sorted(dest.iterdir()) if p.is_file()},
           "evidence_referenced": {f: (md5(C.ROOT / f) if (C.ROOT / f).exists() else "MISSING") for f in referenced_files(dataset)}}
    (dest / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return C.rel(dest), man
