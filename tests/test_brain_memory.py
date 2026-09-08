import tempfile
import unittest
from pathlib import Path

import brain_memory as bm


class BrainMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.roots = {"vault": base / "vault", "projects": base / "projects"}
        self.roots["vault"].mkdir()
        self.roots["projects"].mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, text, root="vault"):
        target = self.roots[root] / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def test_rejects_path_escape_and_non_markdown(self):
        with self.assertRaises(ValueError):
            bm.resolve_note_path("../secret.md", roots=self.roots)
        with self.assertRaises(ValueError):
            bm.resolve_note_path("note.txt", roots=self.roots)

    def test_reads_section_metadata_hash_and_freshness_warning(self):
        self.write(
            "Patterns/sample.md",
            "---\n"
            'title: "Sample"\n'
            'type: "procedure"\n'
            'status: "superseded"\n'
            'superseded_by: "[[new-sample]]"\n'
            "---\n\n"
            "# Sample\n\n## Root cause\n\nWatchdog restart.\n\n## Fix\n\nDisable it.\n",
        )
        result = bm.read_note("Patterns/sample.md", section="Root cause", roots=self.roots)
        self.assertIn("Watchdog restart", result["content"])
        self.assertNotIn("Disable it", result["content"])
        self.assertEqual(result["metadata"]["type"], "procedure")
        self.assertEqual(len(result["sha256"]), 64)
        self.assertTrue(any("superseded" in warning for warning in result["warnings"]))

    def test_append_and_hash_guarded_replace_with_backup(self):
        self.write("Projects/app.md", "---\ntitle: app\nstatus: verified\n---\n\n# App\n\nOld.\n")
        first = bm.read_note("Projects/app.md", roots=self.roots)
        appended = bm.update_note(
            "Projects/app.md", "New observation.", heading="Observed",
            expected_sha256=first["sha256"], roots=self.roots,
        )
        self.assertNotEqual(first["sha256"], appended["sha256"])
        with self.assertRaises(RuntimeError):
            bm.update_note(
                "Projects/app.md", "Stale write.", expected_sha256=first["sha256"],
                roots=self.roots,
            )
        with self.assertRaises(ValueError):
            bm.update_note(
                "Projects/app.md", "# Replacement", mode="replace_body", roots=self.roots,
            )
        current = bm.read_note("Projects/app.md", roots=self.roots)
        replaced = bm.update_note(
            "Projects/app.md", "# App\n\nReplacement.", mode="replace_body",
            expected_sha256=current["sha256"], roots=self.roots,
        )
        self.assertTrue(Path(replaced["backup"]).is_file())
        final = bm.read_note("Projects/app.md", roots=self.roots)
        self.assertIn("Replacement", final["content"])
        self.assertEqual(final["metadata"]["title"], "app")

    def test_verified_memory_requires_evidence_and_uses_typed_folder(self):
        with self.assertRaises(ValueError):
            bm.save_memory(
                "Missing evidence", "Lesson", memory_type="procedure", roots=self.roots,
            )
        saved = bm.save_memory(
            "Watchdog recovery pattern",
            "Check supervisors before repeatedly killing a process.",
            memory_type="procedure",
            evidence="Observed task reactivated Docker services after five minutes.",
            sources=["scheduled-task-state", "port-probe"],
            applies_when="A stopped service unexpectedly returns.",
            project="AI Council",
            roots=self.roots,
        )
        self.assertEqual(saved["path"], "Cowork/Patterns/watchdog-recovery-pattern.md")
        note = bm.read_note(saved["path"], roots=self.roots)
        self.assertEqual(note["metadata"]["status"], "verified")
        self.assertEqual(note["metadata"]["type"], "procedure")
        self.assertIn("Applies when", note["content"])

    def test_feedback_is_append_only(self):
        first = bm.record_feedback(
            "Projects/app.md", "stale", "The port changed.", query="app port",
            roots=self.roots,
        )
        second = bm.record_feedback(
            "Projects/app.md", "helpful", "The source path was correct.", query="app source",
            roots=self.roots,
        )
        self.assertEqual(first["path"], second["path"])
        note = bm.read_note(first["path"], roots=self.roots)
        self.assertIn("The port changed", note["content"])
        self.assertIn("source path was correct", note["content"])


if __name__ == "__main__":
    unittest.main()
