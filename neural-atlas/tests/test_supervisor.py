import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atlas_supervisor import Supervisor


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config.json").write_text(json.dumps({"port": 5190}))
        self.launches = []
        self.now = 1000

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, state):
        return Supervisor(self.root, probe=lambda: dict(state), launch=lambda: self.launches.append(1) or 123, clock=lambda: self.now)

    def pause(self):
        (self.root / "data").mkdir(exist_ok=True)
        db = sqlite3.connect(self.root / "data/atlas.sqlite3")
        try:
            db.execute("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)")
            db.execute("INSERT INTO settings VALUES('paused','true')")
            db.commit()
        finally:
            db.close()

    def test_healthy_worker_is_reused(self):
        result = self.make({"state": "healthy", "worker_pid": 42}).cycle()
        self.assertEqual(result["worker_pid"], 42)
        self.assertEqual(self.launches, [])

    def test_missing_worker_is_started(self):
        result = self.make({"state": "missing"}).cycle()
        self.assertEqual(result["state"], "started_worker")
        self.assertEqual(len(self.launches), 1)

    def test_cold_start_does_not_spawn_duplicates(self):
        s = self.make({"state": "missing"})
        s.cycle()
        self.now += 30
        self.assertEqual(s.cycle()["state"], "starting")
        self.assertEqual(len(self.launches), 1)
        self.now += 120
        s.cycle()
        self.assertEqual(len(self.launches), 2)

    def test_saved_pause_prevents_restart(self):
        self.pause()
        result = self.make({"state": "missing"}).cycle()
        self.assertTrue(result["restart_suppressed"])
        self.assertEqual(self.launches, [])

    def test_foreign_or_slow_listener_is_not_replaced(self):
        for state in ["foreign_listener", "foreign_or_unhealthy_listener", "unreachable"]:
            self.assertEqual(self.make({"state": state}).cycle()["state"], state)
        self.assertEqual(self.launches, [])

    def test_launch_failure_retained_and_backed_off(self):
        s = self.make({"state": "missing"})
        s.launch = lambda: (_ for _ in ()).throw(ValueError("Runtime temporarily missing"))
        self.assertEqual(s.cycle()["state"], "launch_error")
        self.now += 30
        self.assertEqual(s.cycle()["state"], "starting")
        status = json.loads((self.root / "data/supervisor-status.json").read_text())
        self.assertEqual(status["state"], "starting")
        self.assertIn("Runtime temporarily missing", (self.root / "data/supervisor.log").read_text())

    def test_unchanged_healthy_checks_do_not_flood_log(self):
        s = self.make({"state": "healthy", "worker_pid": 42})
        s.cycle()
        first = (self.root / "data/supervisor.log").read_text()
        s.cycle()
        self.assertEqual((self.root / "data/supervisor.log").read_text(), first)


if __name__ == "__main__":
    unittest.main()
