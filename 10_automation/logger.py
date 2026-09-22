"""Run logging: human-readable log + JSON-lines events in 05_evidence/research_logs/<run_date>/."""
import json
import logging
import sys
import time
from datetime import datetime, timezone

import config as C

_events = None


def setup(run_id, run_date, name="run"):
    global _events
    d = C.RESEARCH_LOGS / run_date; d.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("kwc"); log.setLevel(logging.INFO); log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(d / f"{name}_{run_id}.log", encoding="utf-8"); fh.setFormatter(fmt); log.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); log.addHandler(sh)
    _events = d / f"{name}_{run_id}.events.jsonl"
    return log


def get():
    return logging.getLogger("kwc")


def event(stage, status, **data):
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "stage": stage, "status": status, **data}
    if _events:
        with open(_events, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    get().info(f"[{stage}] {status} " + " ".join(f"{k}={v}" for k, v in data.items() if k != "detail"))


class Timer:
    def __enter__(self):
        self.t0 = time.time(); return self

    def __exit__(self, *a):
        self.seconds = round(time.time() - self.t0, 1)
