"""Tests for the Keyword Check - Kobiga automation.

    python 10_automation/test_automation.py            # all offline tests (no eBay, no PH writes; DB read-only where used)
    python 10_automation/test_automation.py -k Resume  # one group

Every test that writes redirects the project paths into a temporary folder (Sandbox), so the real status file,
report, archive and PH Dashboard are never touched."""
import contextlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculate_ranks as R  # noqa: E402
import config as C  # noqa: E402
import detect_changes  # noqa: E402
import extract_keywords as K  # noqa: E402
import generate_dashboard as G  # noqa: E402
import map_products as M  # noqa: E402
import publish  # noqa: E402
import research  # noqa: E402
import run as RUN  # noqa: E402
import validate_dashboard as V  # noqa: E402

REAL_ROOT = C.ROOT
PATH_ATTRS = ["DB_EVIDENCE", "PRODUCT_MAPPING", "KEYWORD_MAPPING", "SEARCH_RESULTS", "COMPETITOR_LISTINGS", "DESCRIPTIONS", "KEYWORD_EVIDENCE",
              "VALIDATION", "RESEARCH_LOGS", "SCREENSHOTS", "REPORT", "STAGING", "ARCHIVE", "STATUS_FILE", "LAST_SUCCESS_FILE", "LOCK_FILE", "PH_PUBLISH_LOG"]


@contextlib.contextmanager
def Sandbox():
    tmp = Path(tempfile.mkdtemp(prefix="kwc_test_"))
    saved = {a: getattr(C, a) for a in PATH_ATTRS + ["ROOT"]}; saved_ph = publish.PH_STATE
    try:
        for a in PATH_ATTRS: setattr(C, a, tmp / Path(getattr(C, a)).relative_to(REAL_ROOT))
        C.ROOT = tmp; publish.PH_STATE = C.RESEARCH_LOGS / "ph_state.json"
        yield tmp
    finally:
        for a, v in saved.items(): setattr(C, a, v)
        publish.PH_STATE = saved_ph
        shutil.rmtree(tmp, ignore_errors=True)


class Scope(unittest.TestCase):
    def test_real_scope_is_the_12_approved_ids(self):
        s = C.load_scope()
        self.assertEqual(len(s["product_ids"]), 12)
        self.assertIn("267765767284", s["product_ids"]); self.assertNotIn("267765726284", s["product_ids"])

    def _bad(self, change):
        d = json.loads(C.SCOPE_FILE.read_text(encoding="utf-8")); change(d)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f: json.dump(d, f)
        try:
            with self.assertRaises(ValueError): C.load_scope(f.name)
        finally: os.remove(f.name)

    def test_rejected_id_refused(self): self._bad(lambda d: d["product_ids"].__setitem__(6, "267765726284"))
    def test_duplicate_refused(self): self._bad(lambda d: d["product_ids"].append(d["product_ids"][0]))
    def test_malformed_refused(self): self._bad(lambda d: d["product_ids"].append("12ab"))


class Mapping(unittest.TestCase):
    rec = lambda self, **k: {"product_id": "1", "found": True, "sku": "A", "listing_skus": ["A", "B"], "ebay_category_path": "Home:Lighting:Wall Lights", **k}

    def test_sot_first(self):
        m = M.map_one(self.rec(), {"A": "Wall Sconce", "B": "Wall Sconce"})
        self.assertEqual((m["mapping_source"], m["product_subtype"], m["search_term"]), ("SOT_SUBTYPE", "Wall Sconce", "LED Wall Sconce"))

    def test_sot_product_subtype_beats_sub_type(self):
        sot = M.sot_by_sku([{"sku": "A", "key": "sub_type", "value": "X"}, {"sku": "A", "key": "product_subtype", "value": "Y"}, {"sku": "B", "key": "product_subtype", "value": "[VERIFY] z"}])
        self.assertEqual(sot, {"A": "Y"})

    def test_category_fallback_never_title(self):
        m = M.map_one(self.rec(product_name="Pendant Light something"), {})
        self.assertEqual((m["mapping_source"], m["product_subtype"]), ("EBAY_CATEGORY", "Wall Lights"))

    def test_not_verified(self):
        m = M.map_one(self.rec(ebay_category_path=None), {})
        self.assertEqual((m["mapping_status"], m["search_term"]), ("NOT VERIFIED", None))

    def test_search_term_rule(self):
        self.assertEqual(M.search_term("Wall Lights", "Home:Lighting:Wall Lights")[0], "LED Wall Lights")
        self.assertEqual(M.search_term("LED Strips", "Home:Lighting:LED Strips")[0], "LED Strips")
        self.assertEqual(M.search_term("Electrical Wires & Cables", "Home:DIY Materials:Electrical Supplies:Electrical Wires & Cables")[0], "Electrical Wires & Cables")


class Keywords(unittest.TestCase):
    def test_matcher_boundaries(self):
        m = R.matcher("Wall Light")
        self.assertTrue(m.search("Modern wall lights for bedroom")); self.assertTrue(m.search("Wall-Light"))
        self.assertFalse(m.search("Wall Lighting")); self.assertFalse(R.matcher("lamp").search("lampshade"))

    def test_rank_counts_listings_once_and_never_estimates(self):
        texts = [("1", "LED Wall Light", "wall light wall light"), ("2", "Sconce", "no"), ("3", "Wall Lights x2", "")]
        self.assertEqual(R.rank("Wall Light", texts)["keyword_rank"], 2)
        self.assertEqual(R.rank("Wall Light", [])["keyword_rank"], "NOT VERIFIED")

    def test_extraction_needs_two_titles_and_uses_own_evidence_only(self):
        ev = {"product_name": "Industrial Wall Light", "screening_profile": {"heads": ["light"]},
              "final_competitors": [{"title": "Vintage Wall Light Black E27"}, {"title": "Wall Light Black Sconce E27"}, {"title": "Brass Lamp"}]}
        kw = K.keywords_for(ev)
        allk = [k["keyword"] for g in kw.values() for k in g]
        # 'Wall Light' is dropped because the longer 'Wall Light Black' occurs in the same number of titles (documented rule)
        self.assertIn("Wall Light Black", allk); self.assertNotIn("Wall Light", allk); self.assertNotIn("Brass", allk)
        self.assertEqual(K.keywords_for({**ev, "final_competitors": ev["final_competitors"][:1]}), {})

    def test_builder_and_independent_validator_agree_on_all_imported_evidence(self):
        n = 0
        for f in (C.KEYWORD_EVIDENCE).glob("imported_*/*.json"):
            ev = json.loads(f.read_text(encoding="utf-8"))
            texts = [(V.raw_title(c["raw_item_page"]), R.clean_description((C.ROOT / c["raw_description"]).read_text(encoding="utf-8")) if c.get("raw_description") else "")
                     for c in ev["final_competitors"]]
            for g in K.GROUPS:
                for k in ev["keywords"].get(g, []):
                    self.assertEqual(k["keyword_rank"], sum(V.uses(t, k["keyword"]) or V.uses(d, k["keyword"]) for t, d in texts), (ev["product_id"], k["keyword"])); n += 1
        self.assertGreater(n, 50)


class Changes(unittest.TestCase):
    def test_classes(self):
        a = {"records": [{"product_id": "1", "sku": "A"}, {"product_id": "2", "sku": "B"}, {"product_id": "9", "sku": "Z"}]}
        b = {"records": [{"product_id": "1", "sku": "A"}, {"product_id": "2", "sku": "B2"}, {"product_id": "3", "sku": "C"}]}
        c = detect_changes.compare(a, b)
        self.assertEqual({k: v["class"] for k, v in c.items()}, {"1": "UNCHANGED", "2": "CHANGED", "3": "NEW", "9": "REMOVED"})
        self.assertEqual(c["2"]["fields"], ["sku"])
        self.assertTrue(all(v["class"] == "NEW" for v in detect_changes.compare(None, b).values()))


def fake_todo(n=3):
    return [({"product_id": f"10000000000{i}", "sku": "S", "product_name": "Wall Light"},
             {"product_subtype": "Wall Lights", "mapping_source": "EBAY_CATEGORY", "search_term": "LED Wall Lights", "search_term_rule": "t"}) for i in range(n)]


def fake_ev(r, day, run_id):
    return {"product_id": r["product_id"], "origin": "LIVE", "run_date": day, "run_id": run_id, "captured_at": "2026-01-01T00:00:00+00:00",
            "research_status": "RESEARCHED", "verification_status": "VERIFIED", "final_competitors": [{}, {}, {}]}


class Resume(unittest.TestCase):
    def setUp(self):
        research.check_uk = lambda pg: {"country": "GB"}      # fake exit check (no browser)
        research.L.event = lambda *a, **k: None

    def test_crash_mid_run_then_resume_skips_completed(self):
        with Sandbox():
            day, calls = "2026-01-01", []
            todo = fake_todo(3)

            def crash_on_second(pg, r, m, d, run_id, exit_ip, conn, stores):
                calls.append(r["product_id"])
                if len(calls) == 2: raise KeyboardInterrupt("machine restart")
                return fake_ev(r, d, run_id)
            research.research_one = crash_on_second
            st = research.load_status()
            with self.assertRaises(KeyboardInterrupt):
                research.research_loop(None, todo, day, "run1", None, set(), st, {"results": {}, "stopped": None})
            st = research.load_status()
            self.assertEqual(st[todo[0][0]["product_id"]]["status"], "VERIFIED")
            self.assertEqual(st[todo[1][0]["product_id"]]["status"], "IN_PROGRESS")
            # resume: only IDs that are not finished today are researched again
            again = [(r, m) for r, m in todo if research.needs_research(st, r["product_id"], day)]
            calls.clear(); research.research_one = lambda pg, r, m, d, run_id, *a: calls.append(r["product_id"]) or fake_ev(r, d, run_id)
            research.research_loop(None, again, day, "run2", None, set(), st, {"results": {}, "stopped": None})
            self.assertEqual(calls, [todo[1][0]["product_id"], todo[2][0]["product_id"]])
            st = research.load_status()
            self.assertTrue(all(st[r["product_id"]]["status"] == "VERIFIED" for r, _ in todo))
            self.assertEqual(st[todo[1][0]["product_id"]]["attempts"], 2)
            # same-day rerun: nothing left to do (idempotent)
            self.assertFalse(any(research.needs_research(st, r["product_id"], day) for r, _ in todo))
            # next day: everything is due again, last_verified kept
            self.assertTrue(all(research.needs_research(st, r["product_id"], "2026-01-02") for r, _ in todo))

    def test_blocked_is_not_verified_retryable_and_stops(self):
        with Sandbox():
            day = "2026-01-01"; todo = fake_todo(3); calls = []

            def blocked(pg, r, *a):
                calls.append(r["product_id"]); raise research.Blocked("https://signin.ebay.co.uk/captcha")
            research.research_one = blocked
            st = research.load_status(); out = {"results": {}, "stopped": None}
            research.research_loop(None, todo, day, "run1", None, set(), st, out)
            self.assertEqual(len(calls), 1); self.assertEqual(out["stopped"], "blocked")
            cur = research.load_status()[todo[0][0]["product_id"]]
            self.assertEqual((cur["status"], cur["retryable"]), ("NOT_VERIFIED", True))
            self.assertTrue(research.needs_research(research.load_status(), todo[0][0]["product_id"], day))

    def test_uk_exit_failure_marks_failed_without_research(self):
        with Sandbox():
            research.check_uk = lambda pg: (_ for _ in ()).throw(research.ExitNotUK("exit country US"))
            research.research_one = lambda *a: self.fail("must not research without a UK exit")
            st = {}; out = {"results": {}, "stopped": None}
            research.research_loop(None, fake_todo(2), "2026-01-01", "r", None, set(), st, out)
            self.assertEqual(set(out["results"].values()), {"FAILED"}); self.assertIn("UK exit", out["stopped"])


class Publish(unittest.TestCase):
    def test_local_publish_refuses_unvalidated_or_changed_file_and_keeps_live(self):
        with Sandbox() as tmp:
            C.REPORT.parent.mkdir(parents=True); C.REPORT.write_text("OLD LIVE", encoding="utf-8")
            staged = tmp / "s.html"; staged.write_text("NEW", encoding="utf-8")
            good_md5 = publish.md5_of(staged)
            self.assertEqual(publish.publish_local(staged, {"overall": "FAIL", "html_md5": good_md5})["result"], "REFUSED")
            self.assertEqual(publish.publish_local(staged, {"overall": "PASS", "html_md5": "0" * 32})["result"], "REFUSED")
            self.assertEqual(C.REPORT.read_text(encoding="utf-8"), "OLD LIVE")
            self.assertEqual(publish.publish_local(staged, {"overall": "PASS", "html_md5": good_md5})["result"], "PUBLISHED")
            self.assertEqual(C.REPORT.read_text(encoding="utf-8"), "NEW")

    def test_ph_publish_only_pending_validated_version(self):
        with Sandbox():
            self.assertEqual(publish.publish_ph("r1")["result"], "NOTHING_PENDING")
            C.REPORT.parent.mkdir(parents=True); C.REPORT.write_text("X", encoding="utf-8")
            C.write_json_atomic(publish.PH_STATE, {"pending": {"run_id": "r0", "md5": "0" * 32, "ids": [], "description": ""}})
            self.assertEqual(publish.publish_ph("r1")["result"], "REFUSED")          # live file is not the validated version
            C.write_json_atomic(publish.PH_STATE, {"pending": {"run_id": "r0", "md5": publish.md5_of(C.REPORT), "ids": [], "description": ""}})
            saved = {v: os.environ.pop(v, None) for v in C.PH_DB_ENVS}
            try:
                r = publish.publish_ph("r1")
                self.assertEqual(r["result"], "FAILED"); self.assertIn("credentials", r["error"])
                self.assertIn("pending", publish.load_state())                       # stays pending -> retried next run
            finally:
                for k, v in saved.items():
                    if v is not None: os.environ[k] = v


class RunStatus(unittest.TestCase):
    """VPN / browser / CAPTCHA problems must be visible (exit 4), and retry slots must not redo finished work."""
    ok_local, ds_cf, ds_cur = {"result": "PUBLISHED"}, {"rows": [{"freshness": "CARRIED FORWARD from 2026-09-22"}]}, {"rows": [{"freshness": "CURRENT"}]}

    def test_research_problem_classes(self):
        self.assertEqual(RUN.research_problem({"todo": ["1"], "stopped": "browser not reachable at http://127.0.0.1:9222: Error", "results": {"1": "FAILED"}}), "RESEARCH_FAILED_BROWSER")
        self.assertEqual(RUN.research_problem({"todo": ["1"], "stopped": "UK exit check failed: ExitNotUK: exit country LK", "results": {"1": "FAILED"}}), "RESEARCH_FAILED_VPN")
        self.assertEqual(RUN.research_problem({"todo": ["1", "2"], "stopped": "blocked", "results": {"1": "NOT_VERIFIED (blocked)"}}), "RESEARCH_BLOCKED_CAPTCHA")
        self.assertEqual(RUN.research_problem({"todo": ["1", "2"], "stopped": None, "results": {"1": "VERIFIED", "2": "FAILED"}}), "RESEARCH_PARTIAL_FAILED")
        self.assertIsNone(RUN.research_problem({"todo": ["1"], "stopped": None, "results": {"1": "VERIFIED"}}))
        self.assertIsNone(RUN.research_problem({"todo": [], "stopped": None, "results": {}}))
        self.assertIsNone(RUN.research_problem({"todo": ["1"], "stopped": "dry-run: no browser", "results": {}}))

    def test_vpn_off_is_a_visible_failure_but_publish_problems_rank_higher(self):
        vpn = {"todo": ["1"], "stopped": "UK exit check failed: exit country LK", "results": {"1": "FAILED"}}
        self.assertEqual(RUN.final_status(vpn, self.ds_cf, self.ok_local, {"result": "PUBLISHED"}, False), "RESEARCH_FAILED_VPN")
        self.assertEqual(RUN.EXIT["RESEARCH_FAILED_VPN"], 4)
        self.assertEqual(RUN.final_status(vpn, self.ds_cf, self.ok_local, {"result": "FAILED"}, False), "PUBLISH_FAILED")
        self.assertEqual(RUN.final_status({"todo": ["1"], "results": {"1": "VERIFIED"}}, self.ds_cur, self.ok_local, {"result": "PUBLISHED"}, False), "SUCCESS")

    def test_retry_slot_skips_only_when_everything_done_and_published_today(self):
        with Sandbox():
            day = "2026-01-01"
            snap = {"records": [{"product_id": "1", "found": True, "listing_status": "Active", "is_ended": 0}]}
            mapping = [{"product_id": "1", "mapping_status": "VERIFIED"}]
            st = {}; research.set_status(st, "1", day, "r", "FAILED", retryable=True); research.save_status(st)
            C.write_json_atomic(C.LAST_SUCCESS_FILE, {"run_date": day, "research_complete": False})
            self.assertFalse(RUN.already_complete(snap, mapping, day))            # 08:45 VPN was off -> retry slot must research
            research.set_status(st, "1", day, "r2", "VERIFIED"); research.save_status(st)
            self.assertFalse(RUN.already_complete(snap, mapping, day))            # researched but dashboard not yet published with it
            C.write_json_atomic(C.LAST_SUCCESS_FILE, {"run_date": day, "research_complete": True})
            self.assertTrue(RUN.already_complete(snap, mapping, day))             # nothing left -> no eBay, no rebuild
            self.assertFalse(RUN.already_complete(snap, mapping, "2026-01-02"))   # next day starts fresh


class Lock(unittest.TestCase):
    def test_second_run_is_refused_and_stale_lock_cleared(self):
        with Sandbox():
            self.assertIsNone(RUN.acquire_lock("a"))
            self.assertEqual(RUN.acquire_lock("b")["run_id"], "a")                   # held by this live process
            RUN.release_lock()
            C.LOCK_FILE.write_text(json.dumps({"pid": 999999, "run_id": "dead"}), encoding="utf-8")
            self.assertIsNone(RUN.acquire_lock("c")); RUN.release_lock()             # stale lock replaced


class Dashboard(unittest.TestCase):
    def test_build_is_deterministic_and_validates_offline(self):
        """Idempotency of rows/competitors/keywords + validator on the real imported evidence (no DB, no browser)."""
        snap_f = sorted(C.DB_EVIDENCE.glob("*/source_snapshot_*.json"))[-1]
        snap = json.loads(snap_f.read_text(encoding="utf-8"))
        mapping = M.map_all(snap)
        a = G.build_dataset(snap, mapping, "2099-01-01", "t1", {}); b = G.build_dataset(snap, mapping, "2099-01-01", "t1", {})
        a["_meta"].pop("built_at"); b["_meta"].pop("built_at")
        self.assertEqual(a, b)
        self.assertEqual([r["product_id"] for r in a["rows"]], C.load_scope()["product_ids"])
        comp_keys = [(r["product_id"], c["listing_id"]) for r in a["rows"] for c in r["final_competitors"]]
        self.assertEqual(len(comp_keys), len(set(comp_keys)))
        self.assertTrue(all(r["freshness"] != "CURRENT" for r in a["rows"]))      # no live research on that day -> never CURRENT
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.html"; a["_meta"]["built_at"] = "2099-01-01T00:00:00+00:00"; p.write_text(G.render(a), encoding="utf-8")
            v = V.validate(p, C.load_scope(), "2099-01-01", "t1", browser=False, db=False)
            self.assertEqual(v["overall"], "PASS", [c for c in v["checks"] if c["result"] == "FAIL"])
            # tampering: one wrong Rank, one extra Product ID row, one row falsely labelled CURRENT -> each must FAIL
            k0 = next(k for r in a["rows"] for g in K.GROUPS for k in r["keywords"][g] if isinstance(k["keyword_rank"], int))
            k0["keyword_rank"] += 1; p.write_text(G.render(a), encoding="utf-8"); k0["keyword_rank"] -= 1
            bad = V.validate(p, C.load_scope(), "2099-01-01", "t1", browser=False, db=False)
            self.assertEqual(bad["overall"], "FAIL"); self.assertIn("Every Keyword Rank equals an independent recount over raw titles + descriptions", [c["check"] for c in bad["checks"] if c["result"] == "FAIL"])
            extra = json.loads(json.dumps(a)); extra["rows"].append({**extra["rows"][0], "product_id": "999999999999"}); p.write_text(G.render(extra), encoding="utf-8")
            self.assertIn("Dashboard Product IDs == scope.json IDs (none missing, none extra, same order)",
                          [c["check"] for c in V.validate(p, C.load_scope(), "2099-01-01", "t1", browser=False, db=False)["checks"] if c["result"] == "FAIL"])
            fake = json.loads(json.dumps(a)); fake["rows"][0]["freshness"] = "CURRENT"; p.write_text(G.render(fake), encoding="utf-8")
            self.assertIn("No row labelled CURRENT unless its evidence is LIVE research from this run date",
                          [c["check"] for c in V.validate(p, C.load_scope(), "2099-01-01", "t1", browser=False, db=False)["checks"] if c["result"] == "FAIL"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
