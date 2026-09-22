"""Configuration for the Keyword Check - Kobiga daily automation.

No secrets here. Connection strings and credentials come from environment variables only:
    WLP_SOURCE_DB_URL                              read-only source database (listings, SOT, seller stores)
    PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD     PH Dashboard publish (tech_team_outputs.ph_task)
Other settings may be overridden with KWC_* environment variables.
Scope (the approved Product IDs) lives in 10_automation/scope.json - see load_scope()."""
import json
import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("KWC_ROOT", Path(__file__).resolve().parent.parent))

# numbered project folders (workflow order; single definition - every stage uses these names)
F = {"requirements": "00_requirements", "prompts": "01_prompts", "source_mapping": "02_source_mapping", "sql": "03_sql",
     "research": "04_research", "evidence": "05_evidence", "validation": "06_validation", "report": "07_report",
     "handover": "08_handover", "closure": "09_closure", "automation": "10_automation", "archive": "11_archive"}

AUTOMATION = ROOT / F["automation"]
SCOPE_FILE = AUTOMATION / "scope.json"
SQL_DIR = ROOT / F["sql"]
REQUIREMENT_CSV = ROOT / F["requirements"] / "System Task - Keyword check- Kobiga.csv"
METHOD_PDF = ROOT / F["requirements"] / "Keyword Analysis.pdf"

# output folders (each stage creates its dated sub-folder on demand)
DB_EVIDENCE = ROOT / F["evidence"] / "database"
PRODUCT_MAPPING = ROOT / F["source_mapping"] / "product_mapping"
KEYWORD_MAPPING = ROOT / F["source_mapping"] / "keyword_mapping"
POPULATION = ROOT / F["source_mapping"] / "population"
SEARCH_RESULTS = ROOT / F["research"] / "search_results"
COMPETITOR_LISTINGS = ROOT / F["research"] / "competitor_listings"
DESCRIPTIONS = ROOT / F["research"] / "descriptions"
KEYWORD_EVIDENCE = ROOT / F["research"] / "keyword_evidence"
VALIDATION = ROOT / F["validation"]
RESEARCH_LOGS = ROOT / F["evidence"] / "research_logs"
SCREENSHOTS = ROOT / F["evidence"] / "screenshots"
REPORT = ROOT / F["report"] / "keyword_check_kobiga.html"
STAGING = ROOT / F["report"] / ".staging"
ARCHIVE = ROOT / F["archive"]
STATUS_FILE = RESEARCH_LOGS / "research_status.json"
LAST_SUCCESS_FILE = RESEARCH_LOGS / "last_success.json"
LOCK_FILE = RESEARCH_LOGS / "run.lock"
PH_PUBLISH_LOG = DB_EVIDENCE / "ph_publish_log.jsonl"

# environment variable NAMES (values are never stored or logged)
SOURCE_DB_ENV = "WLP_SOURCE_DB_URL"
PH_DB_ENVS = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")

DB_CONNECT_TIMEOUT = int(os.environ.get("KWC_DB_CONNECT_TIMEOUT", 30))
DB_RETRIES = int(os.environ.get("KWC_DB_RETRIES", 3))

# browser / research (Keyword Analysis.pdf steps 1-7)
CDP_URL = os.environ.get("KWC_CDP_URL", "http://127.0.0.1:9222")
REQUIRED_EXIT_COUNTRY = os.environ.get("KWC_REQUIRED_COUNTRY", "GB")
EXIT_CHECK_URL = "https://ipinfo.io/json"
UK_CHECK_EVERY = int(os.environ.get("KWC_UK_CHECK_EVERY", 5))       # re-check exit country every N Product IDs
SEARCH_URL = "https://www.ebay.co.uk/sch/i.html?_nkw={q}&LH_BIN=1&LH_ItemCondition=3&LH_PrefLoc=1&_pgn={p}"
SEARCH_FILTERS = ("LH_BIN=1", "LH_ItemCondition=3", "LH_PrefLoc=1")  # Buy It Now, New, Item Location UK Only
SEARCH_PAGES = (1, 2, 3)
ITEM_URL = "https://www.ebay.co.uk/itm/{lid}"
SHORTLIST = int(os.environ.get("KWC_SHORTLIST", 6))                 # PDF step 5: 6-8
FINAL_MAX = int(os.environ.get("KWC_FINAL_MAX", 5))                 # PDF step 7: 3-5
VERIFIED_MIN = 3
PARTIAL_MIN = 2
PAGE_PAUSE_S = float(os.environ.get("KWC_PAGE_PAUSE_S", 1.5))
# internal accounts (PDF step 4 names Ledsone, Electricalsone, sunsone; the other tokens are our own stores too).
# Also excluded: every store in ebay_campaigns.seller_stores and any candidate listing ID that is ours in the DB.
INTERNAL_TOKENS = ("ledsone", "led_sone", "electricalsone", "sunsone", "lightingsone")

# SOT attribute keys, in priority order (build_population_mapping.py rule)
SOT_SUBTYPE_KEYS = ("product_subtype", "sub_type")
SKU_PLACEHOLDERS = {"sku not assigneds"}

# PH Dashboard (tech_team_outputs.ph_task) - confirmed by the user 2026-09-22 (WORKFLOW_DESIGN.md D4)
PH = {"project_code": "KWC", "project_name": "Keyword Check", "task_name": "Keyword Check Dashboard",
      "team": "ebay_priors", "assigned_user_team": "ebay_priors", "developer": "Apirame",
      "phase_level": 1, "version_level": 1, "version_status": "released",
      "users": ["genga", "Jarsini", "kobiga", "powsteena", "Sharmilan", "Sivajitha", "Thasanan", "Thinesh"]}

# one-time history import (user decision D6, 2026-09-22). Read-only source.
IMPORT_SOURCE = Path(os.environ.get("KWC_IMPORT_SOURCE", r"C:\Users\LED 222\Keywords check"))

SCHEDULE_TASK_NAME = "KeywordCheckKobiga_Daily"
SCHEDULE_TIME = "08:45"

ID_RE = re.compile(r"^\d{11,13}$")


def load_scope(path=SCOPE_FILE):
    """Return the scope dict after structural checks. Raises ValueError on any problem."""
    s = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = s.get("product_ids") or []
    problems = []
    if not ids: problems.append("product_ids is empty")
    bad = [i for i in ids if not isinstance(i, str) or not ID_RE.match(i)]
    if bad: problems.append(f"malformed Product IDs: {bad}")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup: problems.append(f"duplicate Product IDs: {dup}")
    rej = sorted(set(ids) & set(s.get("rejected_product_ids") or []))
    if rej: problems.append(f"rejected Product IDs present in scope: {rej}")
    if problems: raise ValueError("; ".join(problems))
    return s


def rel(p):
    """Project-relative POSIX path string (stored in evidence so the project folder can move); absolute if outside."""
    p = Path(p).resolve()
    try: return str(p.relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError: return str(p)


def write_json_atomic(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def unique_path(path):
    """Never overwrite: return path, or path with _r2, _r3 ... if it exists."""
    path = Path(path)
    if not path.exists(): return path
    n = 2
    while (q := path.with_name(f"{path.stem}_r{n}{path.suffix}")).exists(): n += 1
    return q
