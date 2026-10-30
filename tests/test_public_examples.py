"""First-run source evidence must survive short headings and paragraphs."""
from pathlib import Path
import unittest
from test_brain_retrieval import engine


class PublicExampleTests(unittest.TestCase):
    def test_sample_project_is_retrievable_in_current_mode(self):
        rows = []
        e = engine(rows)
        path = 'Projects/sample-app.md'
        text = (Path(__file__).parents[1] / 'examples/vault' / path).read_text(encoding='utf-8')
        chunks = list(e['chunk_text'](text))
        e['register_lex']('vault:' + path, 'vault', path, text, chunks=chunks)
        rows.extend(dict(id='vault:' + path, root='vault', path=path, chunk=c) for c in chunks)
        hits = e['do_search']('sample app', roots='vault', include='Projects', mode='current')
        self.assertEqual(hits[0]['path'], path)
        self.assertIn('fictional local notes application', hits[0]['snippet'])

    def test_chunks_are_exact_contiguous_source_evidence(self):
        e = engine([])
        text = '# A\n\nShort.\n\n' + ('Long source paragraph. ' * 80) + '\n\nDone.'
        chunks = list(e['chunk_text'](text))
        self.assertTrue(all(chunk in text for chunk in chunks))
        self.assertTrue(any('Short.' in chunk for chunk in chunks))
        self.assertTrue(any('Done.' in chunk for chunk in chunks))

    def test_short_meaningful_note_is_not_discarded(self):
        e = engine([])
        self.assertEqual(list(e['chunk_text']('Remember this.')), ['Remember this.'])
