import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import brain_memory as bm


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.roots = {"vault": Path(self.temp.name) / "vault"}
        self.addCleanup(self.temp.cleanup)

    def create(self, **kwargs):
        return bm.save_memory("Revision sample", "Original lesson", memory_type="fact",
                              evidence="fixture observation", roots=self.roots, **kwargs)

    def revise(self, note, **kwargs):
        return bm.save_memory("Revision sample", "Corrected lesson", memory_type="fact",
                              expected_sha256=note["sha256"], roots=self.roots, **kwargs)

    def test_verified_to_stale_updates_metadata_and_retains_backup(self):
        first = self.create(project="Brain")
        result = self.revise(first, status="stale", valid_until="2020-01-01", supersedes=["old.md"])
        self.assertEqual(result["metadata"]["status"], "stale")
        self.assertEqual(result["metadata"]["project"], "Brain")
        self.assertEqual(result["metadata"]["verified_at"], "")
        self.assertEqual(result["metadata"]["supersedes"], ["old.md"])
        self.assertTrue(any("expired" in w for w in result["warnings"]))
        self.assertEqual(bm._hash(Path(result["backup"]).read_text(encoding="utf-8")), first["sha256"])
        self.assertIn("Original lesson", bm.read_note(result["path"], roots=self.roots)["content"])

    def test_promotion_requires_fresh_evidence(self):
        first = self.create(status="proposed")
        with self.assertRaises(ValueError):
            self.revise(first, status="verified")
        result = self.revise(first, status="verified", evidence="new test passed")
        self.assertEqual(result["metadata"]["status"], "verified")
        self.assertTrue(result["metadata"]["verified_at"])

    def test_optional_omission_preserves_and_empty_clears(self):
        first = self.create(status="observed", project="A", valid_until="2099-01-01", sources=["s"])
        second = self.revise(first)
        self.assertEqual(second["metadata"]["project"], "A")
        third = self.revise(second, project="", valid_until="", sources=[])
        self.assertEqual(third["metadata"]["project"], "")
        self.assertEqual(third["metadata"]["sources"], [])
        self.assertEqual(third["metadata"]["valid_until"], "")

    def test_missing_or_stale_hash_rejected(self):
        first = self.create()
        with self.assertRaises(ValueError):
            self.create()
        self.revise(first, status="stale")
        with self.assertRaises(RuntimeError):
            self.revise(first, status="stale")

    def test_concurrent_revisions_only_one_wins(self):
        first = self.create(status="observed")
        def change(_):
            try:
                self.revise(first, status="stale")
                return "saved"
            except RuntimeError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(change, range(2))), ["saved", "conflict"])

    def test_unrelated_nested_yaml_preserved(self):
        first = self.create(status="observed")
        target = Path(first["absolute_path"])
        original = target.read_text(encoding="utf-8").replace("---\n", "---\ncustom:\n  values: [a, b]\n", 1)
        target.write_text(original, encoding="utf-8")
        first = bm.note_info(first["path"], roots=self.roots)
        self.revise(first, status="stale")
        self.assertIn("custom:\n  values: [a, b]\n", target.read_text(encoding="utf-8"))

    def test_slug_collision_rejected(self):
        first = self.create(status="observed")
        with self.assertRaises(ValueError):
            bm.save_memory("Revision sample!", "Other", memory_type="fact", status="observed",
                           expected_sha256=first["sha256"], roots=self.roots)

    def test_invalid_expiry_rejected(self):
        with self.assertRaises(ValueError):
            self.create(valid_until="banana")
