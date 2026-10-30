import copy
import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atlas import Store, Worker, latest_body, make_handler, safe_source
from http.server import ThreadingHTTPServer


class FakeModel:
    def __init__(self, callback=None):
        self.calls = 0
        self.callback = callback

    def classify(self, title, body):
        self.calls += 1
        if self.callback:
            self.callback()
        return {"raw": {"answers": {"kind": {"choice": "solution"}, "review": {"choice": "review"}}}, "device": "cpu", "calibrated": False}


class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.graph = self.root / "graph.json"
        self.graph.write_text('{"nodes":[],"links":[]}')
        self.config = {"vault": str(self.vault), "graph": str(self.graph), "brain_url": "http://127.0.0.1:1", "model_revision": "test", "batch_size": 1, "batch_interval": 1, "scan_interval": 120}
        self.store = Store(self.root, self.config)

    def tearDown(self):
        self.temp.cleanup()

    def note(self, path="a.md", body="# A\nA solved problem."):
        p = self.vault / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def test_unchanged_notes_do_not_reinfer(self):
        self.note()
        self.store.scan()
        model = FakeModel()
        worker = Worker(self.store, model)
        self.assertTrue(worker.one())
        self.store.scan()
        self.assertFalse(worker.one())
        self.assertEqual(model.calls, 1)
        self.assertEqual(self.store.status()["jobs"], {"suggested": 1})

    def test_revision_preserves_result_and_rejects_old_acceptance(self):
        p = self.note()
        self.store.scan()
        Worker(self.store, FakeModel()).one()
        old = self.store.jobs()[0]
        p.write_text("# A\nA changed solution.")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.store.review(old["id"], "accepted", "Read it")
        self.store.scan()
        self.assertEqual(self.store.status()["jobs"], {"stale": 1, "pending": 1})
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0], 2)
            self.assertIsNotNone(db.execute("SELECT result FROM jobs WHERE id=?", (old["id"],)).fetchone()[0])

    def test_edit_during_inference_is_stale(self):
        p = self.note()
        self.store.scan()
        model = FakeModel(lambda: p.write_text("Changed while model was working"))
        Worker(self.store, model).one()
        self.assertEqual(self.store.status()["jobs"], {"stale": 1})

    def test_routine_classification_retained_without_review_inbox(self):
        self.note()
        self.store.scan()
        class RoutineModel:
            def classify(self, title, body):
                return {"raw": {"answers": {"review": {"choice": "routine"}}}}
        Worker(self.store, RoutineModel()).one()
        self.assertEqual(self.store.status()["jobs"], {"triaged": 1})
        self.assertEqual(self.store.jobs(), [])
        self.assertIsNotNone(self.store.detail("note:a.md")["suggestion"]["result"])

    def test_pause_and_resume_persist(self):
        self.note()
        self.store.scan()
        self.store.set("paused", True)
        reopened = Store(self.root, self.config)
        model = FakeModel()
        worker = Worker(reopened, model)
        self.assertFalse(worker.one())
        reopened.set("paused", False)
        self.assertTrue(worker.one())
        self.assertEqual(model.calls, 1)

    def test_crash_recovery_only_by_owner(self):
        self.note()
        self.store.scan()
        with self.store.db() as db:
            db.execute("UPDATE jobs SET state='running'")
        Store(self.root, self.config)  # Read-only CLI construction must not reset active work.
        self.assertEqual(self.store.status()["jobs"], {"running": 1})
        self.store.recover()
        self.assertEqual(self.store.status()["jobs"], {"pending": 1})

    def test_error_visible_and_retryable(self):
        self.note()
        self.store.scan()
        model = FakeModel(lambda: (_ for _ in ()).throw(ValueError("Test failure")))
        Worker(self.store, model).one()
        job = self.store.jobs()[0]
        self.assertEqual(job["error"], "Test failure")
        self.store.review(job["id"], "retry", "Runtime repaired")
        self.assertEqual(self.store.status()["jobs"], {"pending": 1})

    def test_delete_and_reappearance_keep_history(self):
        p = self.note()
        self.store.scan()
        text = p.read_text()
        p.unlink()
        self.store.scan()
        self.assertEqual(self.store.status()["notes"], 0)
        p.write_text(text)
        self.store.scan()
        self.assertEqual(self.store.status()["notes"], 1)
        self.assertEqual(self.store.status()["jobs"], {"pending": 1})

    def test_reverted_revision_reuses_result_and_review(self):
        p = self.note()
        original = p.read_text()
        self.store.scan()
        model = FakeModel()
        worker = Worker(self.store, model)
        worker.one()
        job_id = self.store.jobs()[0]["id"]
        self.store.review(job_id, "accepted", "Original source checked")
        p.write_text("# A\nA different revision.")
        self.store.scan()
        p.write_text(original)
        self.store.scan()
        self.assertFalse(worker.one())
        self.assertEqual(model.calls, 1)
        self.assertEqual(self.store.detail("note:a.md")["suggestion"]["id"], job_id)
        self.assertEqual(self.store.detail("note:a.md")["suggestion"]["state"], "accepted")

    def test_routine_policy_migration_keeps_raw_result(self):
        self.note()
        self.store.scan()
        Worker(self.store, FakeModel()).one()
        with self.store.db() as db:
            db.execute("UPDATE jobs SET result=?", (json.dumps({"raw": {"answers": {"review": {"choice": "routine"}}}}),))
        reopened = Store(self.root, self.config)
        self.assertEqual(reopened.status()["jobs"], {"triaged": 1})
        with reopened.db() as db:
            self.assertIsNotNone(db.execute("SELECT result FROM jobs").fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='routine_queue_policy'").fetchone()[0], 1)

    def test_path_traversal_and_sensitive_exclusions(self):
        for path in ["../outside.md", "C:/outside.md", "/outside.md", ".obsidian/a.md", "VTuber-Memory/a.md", "credentials.md", "graphify-out/a.md"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_source(self.vault, path)
        self.note("credentials.md", "Should never be admitted")
        self.note("VTuber-Memory/hidden.md", "Should never be admitted")
        self.note("private.md", "---\nprivate: true\n---\nDo not admit")
        self.note()
        self.store.scan()
        self.assertEqual(self.store.status()["notes"], 1)

    def test_ambiguous_wikilinks_not_guessed(self):
        self.note("start.md", "# Start\n[[same]] [[folder/same]]")
        self.note("folder/same.md")
        self.note("other/same.md")
        self.store.scan()
        nodes, edges = self.store.all_graph()
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["target"], "note:folder/same.md")

    def test_relative_links_resolve(self):
        self.note("folder/start.md", "# Start\n[[../target]]")
        self.note("target.md")
        self.store.scan()
        self.assertEqual(self.store.all_graph()[1][0]["target"], "note:target.md")

    def test_graph_snapshot_provenance_and_staleness(self):
        p = self.note()
        payload = {"nodes": [{"id": "x", "label": "Concept", "source_file": "Knowledge-Base/a.md"}, {"id": "z", "source_file": "Knowledge-Base/credentials.md"}], "links": []}
        self.graph.write_text(json.dumps(payload))
        self.store.scan()
        node = self.store.detail("graph:x")["node"]
        self.assertEqual(node["origin"], "graphify")
        self.assertFalse(node["stale"])
        p.write_text("# Updated source")
        self.store.scan()
        self.assertTrue(self.store.detail("graph:x")["node"]["stale"])
        self.assertNotIn("graph:z", [n["id"] for n in self.store.all_graph()[0]])

    def test_invalid_graph_retains_previous_import(self):
        self.note()
        self.graph.write_text(json.dumps({"nodes": [{"id": "x", "source_file": "Knowledge-Base/a.md"}], "links": []}))
        self.store.scan()
        self.graph.write_text("bad json")
        self.store.scan()
        self.assertIsNotNone(self.store.status()["graph"]["error"])
        self.assertIn("graph:x", [n["id"] for n in self.store.all_graph()[0]])

    def test_reviews_are_audited_and_do_not_modify_source(self):
        p = self.note()
        before = p.read_bytes()
        self.store.scan()
        Worker(self.store, FakeModel()).one()
        j = self.store.jobs()[0]
        self.store.review(j["id"], "accepted", "Checked supporting note")
        self.store.review(j["id"], "dismissed", "Reconsidered the category")
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(self.store.status()["reviews"], 2)

    def test_handoff_is_bounded_and_source_hashed(self):
        for i in range(11):
            self.note(f"n{i}.md", "# Note\n" + "Evidence " * 1000)
        self.store.scan()
        worker = Worker(self.store, FakeModel())
        for _ in range(11):
            worker.one()
        packet = self.store.packet()
        self.assertEqual(len(packet["items"]), 8)
        for item in packet["items"]:
            self.assertLessEqual(len(item["latest_revision_excerpt"]), 2400)
            self.assertEqual(item["sha256"], hashlib.sha256((self.vault / item["path"]).read_bytes()).hexdigest())

    def test_latest_typed_revision_not_historical_lesson(self):
        self.assertEqual(latest_body("Old\n## Revision — 1\nFirst\n## Revision — 2\nCurrent"), "Current")

    def test_http_controls_reject_cross_origin_and_path_reads(self):
        self.note()
        self.store.scan()
        worker = Worker(self.store, FakeModel())
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store, worker, "test-token"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(method, path, body=None, headers=None):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.request(method, path, json.dumps(body) if body else None, headers or {})
                r = conn.getresponse()
                value = json.loads(r.read())
                status = r.status
                conn.close()
                return status, value
            self.assertEqual(request("POST", "/api/control", {"action": "pause"})[0], 403)
            self.assertEqual(request("POST", "/api/control", {"action": "pause"}, {"X-Atlas-Token": "test-token", "Origin": "https://evil.example"})[0], 403)
            self.assertEqual(request("POST", "/api/control", {"action": "pause"}, {"X-Atlas-Token": "test-token"})[0], 200)
            self.assertTrue(self.store.get("paused"))
            self.assertEqual(request("GET", "/api/note?path=../outside.md")[0], 400)
            status, result = request("GET", "/api/brain/health")
            self.assertEqual(status, 503)
            self.assertFalse(result["available"])
            self.assertEqual(request("GET", "/api/graph")[0], 200)
            self.assertEqual(request("GET", "/api/status", headers={"Host": "attacker.example"})[0], 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == "__main__":
    unittest.main()
