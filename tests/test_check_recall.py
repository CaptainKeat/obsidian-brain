import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_recall.py"
spec = importlib.util.spec_from_file_location("recall", SCRIPT)
recall = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recall)


class RecallChecks(unittest.TestCase):
    def test_same_path_in_wrong_root_does_not_count_as_target(self):
        case = {"roots": "vault", "expected": "Projects/app.md"}
        wrong = {"root": "projects", "path": case["expected"], "snippet": "body"}
        self.assertFalse(recall.evaluate_hits([wrong], case)["passed"])
        self.assertTrue(recall.evaluate_hits([dict(wrong, root="vault")], case)["passed"])

    def test_duplicate_or_metadata_snippet_fails_even_when_target_is_present(self):
        case = {"roots": "vault", "expected": "Projects/app.md"}
        hit = {"root": "vault", "path": case["expected"], "snippet": "body"}
        self.assertFalse(recall.evaluate_hits([hit, hit], case)["passed"])
        self.assertFalse(recall.evaluate_hits([dict(hit, snippet="---\ntitle: app")], case)["passed"])

    def test_protects_indexed_sources_and_existing_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            protected = base / "vault"
            with self.assertRaises(ValueError):
                recall.validate_dest(protected / "report.json", [protected])
            evidence = base / "receipt.json"
            evidence.write_text("keep")
            with self.assertRaises(ValueError):
                recall.validate_dest(evidence, [protected])
            self.assertEqual(evidence.read_text(), "keep")
            recall.validate_dest(base / "new.json", [protected])

    def test_wordless_excerpt_fails_even_with_correct_target(self):
        case = {"roots": "vault", "expected": "Projects/app.md"}
        for snippet in ('#', '___', '```', ''):
            with self.subTest(snippet=snippet):
                hit = {"root":"vault", "path":case["expected"], "snippet":snippet}
                result = recall.evaluate_hits([hit],case)
                self.assertFalse(result["passed"])
                self.assertEqual(result["weak_snippets"],1)


if __name__ == "__main__":
    unittest.main()
