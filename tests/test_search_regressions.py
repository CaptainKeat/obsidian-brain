"""Regressions for evidence fragments and candidate starvation."""
import unittest
import brain_retrieval as br
from test_brain_retrieval import engine


class SearchRegressionTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.e = engine(self.rows)

    def note(self, path, text, chunks=None):
        chunks = chunks or list(self.e["chunk_text"](text))
        self.e["register_lex"]("vault:"+path, "vault", path, text, chunks=chunks)
        self.rows.extend(dict(id="vault:"+path, root="vault", path=path, chunk=c) for c in chunks)

    def search(self, query, **kwargs):
        return self.e["do_search"](query, **kwargs)

    def test_frontmatter_boundary_hash_is_not_a_search_excerpt(self):
        metadata = '---\ntitle: "recovery preference"\nstatus: "observed"\n---\n\n'
        body = '# Recovery preference\n\nKeep useful decisions and verified project checkpoints.'
        self.note("Preferences/continuity.md", metadata+body,
                  chunks=[metadata+'#', body])
        hits = self.search("recovery", k=1)
        self.assertIn("Keep useful decisions", hits[0]["snippet"])
        self.assertNotEqual(hits[0]["snippet"].strip(), '#')

    def test_punctuation_fragment_rejected_without_inventing_evidence(self):
        for marker in ('#', '---', '```', '___', '**'):
            with self.subTest(marker=marker):
                note = br.make_note("vault", "a.md", '---\ntitle: "recovery"\n---\n\n'+marker)
                self.assertEqual(br.body_chunk(note["text"], note), "")
                self.assertEqual(br.body_chunk("stale text not in file", note), "")

    def test_heading_only_fragment_uses_actual_note_context(self):
        metadata = '---\ntitle: "recovery preference"\n---\n\n'
        heading = '# Recovery preference'
        prose = 'Keep useful decisions and verified project checkpoints.'
        text = metadata + heading + '\n\n' + prose
        self.note('Preferences/context.md',text,chunks=[metadata+heading,prose])
        hits = self.search('recovery preference',k=1)
        self.assertIn(prose,hits[0]['snippet'])
        self.assertIn(hits[0]['snippet'],text)

    def test_vector_duplicates_do_not_starve_distinct_notes(self):
        chunks = [f"Large document unrelated context segment {i}." for i in range(120)]
        self.note("large.md", '\n\n'.join(chunks), chunks=chunks)
        for label in ('b','c','d'):
            self.note(label+'.md', 'Different semantically related note '+label)
        hits = self.search("unmatched", k=4)
        self.assertEqual({h["path"] for h in hits}, {'large.md','b.md','c.md','d.md'})
        self.assertEqual(len(hits), 4)

    def test_lexical_window_retains_support_for_vector_title_hit(self):
        text = '---\ntitle: "migration workspace"\n---\n\nmigration workspace ' + 'unrelated filler '*40
        self.note("Projects/workspace.md", text, chunks=[text])
        for i in range(100):
            self.note(f"Projects/rival-{i}.md", 'migration workspace '*8 + str(i))
        hits = self.search("migration workspace", k=5)
        target = next((h for h in hits if h["path"]=="Projects/workspace.md"), None)
        self.assertIsNotNone(target)
        self.assertIn("lexical", target["via"])


if __name__ == "__main__":
    unittest.main()
