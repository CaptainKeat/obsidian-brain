import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import brain_memory as bm
from brain_graph_links import Catalog, hub_path, navigation, repair_links

spec = importlib.util.spec_from_file_location("repair_graph", Path(__file__).resolve().parents[1] / "scripts/repair_graph_links.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class GraphLinksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.vault = self.base / "vault"
        self.vault.mkdir()
        self.roots = {"vault": self.vault, "projects": self.base / "projects"}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rel, text):
        p = self.vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_save_connects_existing_notes_and_hub_without_changing_metadata(self):
        self.write("Cowork/Projects/sample.md", '# Existing\n')
        result = bm.save_memory("Worker recovery", "See [[vault:Cowork/Projects/sample.md#Checks|checks]].",
            memory_type="procedure", status="observed", project="Sample Alpha",
            sources=["vault:Cowork/Projects/sample.md"], roots=self.roots)
        text = (self.vault / result["path"]).read_text()
        self.assertIn("[[Cowork/Projects/sample#Checks|checks]]", text)
        self.assertIn("[[" + hub_path("Sample Alpha")[:-3] + "]]", text)
        metadata, _ = bm.parse_frontmatter(text)
        self.assertEqual(metadata['sources'], ["vault:Cowork/Projects/sample.md"])
        self.assertEqual(metadata['project'], "Sample Alpha")
        self.assertTrue((self.vault / hub_path("Sample Alpha")).is_file())
        current = bm.read_note(result['path'], roots=self.roots)
        bm.save_memory("Worker recovery", "Second observation", memory_type="procedure",
            status="observed", expected_sha256=current['sha256'], roots=self.roots)
        text = (self.vault / result["path"]).read_text()
        self.assertEqual(text.count("<!-- brain-navigation:start -->"), 1)
        self.assertIn("Second observation", text)
        self.assertIn("vault:Cowork/Projects/sample.md", text)

    def test_update_and_legacy_append_keep_hub_and_backup(self):
        from unittest.mock import patch
        import vault_writer
        p = self.write("Cowork/legacy.md", '---\nproject: "Sample Alpha"\n---\nOriginal\n')
        first = bm.read_note("Cowork/legacy.md", roots=self.roots)
        result = bm.update_note("Cowork/legacy.md", "Next", roots=self.roots,
                                expected_sha256=first["sha256"])
        self.assertTrue(Path(result["backup"]).is_file())
        with patch.object(vault_writer, "VAULT", self.vault), patch.object(vault_writer, "OBSIDIAN_API_KEY", None):
            vault_writer.save_note("legacy", "Last", folder="Cowork")
        text = p.read_text()
        self.assertIn("Original", text)
        self.assertIn("Next", text)
        self.assertIn("Last", text)
        self.assertEqual(text.count("<!-- brain-navigation:start -->"), 1)
        self.assertIn("[[" + hub_path("Sample Alpha")[:-3] + "]]", text)

    def test_unique_titles_only_and_protected_content(self):
        self.write("Cowork/projectsalpha.md", '---\ntitle: "Projects/Alpha"\n---\n# Alpha\n')
        self.write("one.md", '---\ntitle: "Ambiguous"\n---\n')
        self.write("two.md", '---\ntitle: "Ambiguous"\n---\n')
        text = ('---\nsources: ["[[vault:Cowork/projectsalpha.md]]"]\n---\n'
                '[[Projects/Alpha]] [[Ambiguous]] [[projects:outside.md]] [[Missing]]\n'
                '`[[Projects/Alpha]]`\n``[[Projects/Alpha]]``\n```md\n[[Projects/Alpha]]\n```\n'
                'Revision metadata: {"sources": ["[[Projects/Alpha]]"]}\n')
        new, fixed, missing = repair_links(text, Catalog(self.vault))
        self.assertEqual(len(fixed), 1)
        self.assertIn('[[Cowork/projectsalpha|Projects/Alpha]]', new)
        self.assertIn('`[[Projects/Alpha]]`', new)
        self.assertIn('``[[Projects/Alpha]]``', new)
        self.assertIn('sources: ["[[vault:Cowork/projectsalpha.md]]"]', new)
        self.assertIn('Revision metadata: {"sources": ["[[Projects/Alpha]]"]}', new)
        self.assertIn("Ambiguous", missing)

    def test_migration_dry_run_idempotence_and_exact_rollback(self):
        p = self.write("Cowork/Projects/checkpoint.md", '---\nproject: "Sample Alpha"\n---\n# Original\n')
        raw = p.read_bytes()
        self.write("INDEX.md", "See [[Missing]].\n")
        plan = migration.plan(self.vault)
        self.assertEqual(raw, p.read_bytes())
        backup = self.base / 'backup'
        result = migration.apply_plan(plan, backup)
        self.assertTrue(all(e['status'] == 'applied' for e in result['entries']))
        self.assertEqual(migration.plan(self.vault)['entries'], [])
        migration.rollback(backup / 'receipt.json')
        self.assertEqual(p.read_bytes(), raw)
        self.assertFalse((self.vault / hub_path('Sample Alpha')).exists())

    def test_migration_conflict_and_rollback_preserve_concurrent_edit(self):
        p = self.write('note.md', '---\nproject: "Sample Alpha"\n---\nOriginal\n')
        plan = migration.plan(self.vault)
        p.write_text('Human edit\n')
        with self.assertRaises(RuntimeError):
            migration.apply_plan(plan, self.base / 'backup-rejected')
        self.assertEqual(p.read_text(), 'Human edit\n')
        plan = migration.plan(self.vault)
        backup = self.base / 'backup'
        migration.apply_plan(plan, backup)
        map_path = self.vault / 'Brain Project Map.md'
        map_path.write_text('Later human edit\n')
        result = migration.rollback(backup / 'receipt.json')
        self.assertEqual(map_path.read_text(), 'Later human edit\n')
        self.assertTrue(any(e['status'] == 'rollback-conflict' for e in result['entries']))

    def test_unsafe_and_cross_root_references_are_not_converted(self):
        self.write('note.md', '# Note')
        catalog = Catalog(self.vault)
        for target in ['../note.md', 'projects:note.md', '/note.md', 'https://site/note.md']:
            self.assertIsNone(catalog.resolve(target))
        text, _, _ = navigation('Body', catalog, sources=['vault:../note.md', 'projects:note.md'])
        self.assertEqual(text, 'Body')

    def test_bare_repository_source_is_not_mistaken_for_vault_note(self):
        self.write('README.md', '# Vault readme')
        text, _, _ = navigation('Body', Catalog(self.vault), sources=['README.md'])
        self.assertEqual(text, 'Body')

    def test_scalar_reference_and_unclosed_code_are_safe(self):
        self.write('note.md', '# Note')
        catalog = Catalog(self.vault)
        text, _, _ = navigation('Body', catalog, sources='vault:note.md')
        self.assertIn('[[note]]', text)
        code = '```md\n[[vault:note.md]]\n'
        self.assertEqual(repair_links(code, catalog)[0], code)

    def test_transient_windows_receipt_lock_retries_only_journal(self):
        from unittest.mock import patch
        receipt = self.base / 'receipt.json'
        real_write = bm._atomic_write
        calls = []
        def transient(path, text):
            calls.append(str(path))
            if len(calls) == 1:
                raise PermissionError('simulated Windows sharing violation')
            return real_write(path, text)
        with patch.object(migration.bm, '_atomic_write', side_effect=transient), patch.object(migration.time, 'sleep'):
            migration.save_receipt(receipt, {'status': 'applied'})
        self.assertEqual(json.loads(receipt.read_text()), {'status': 'applied'})
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
