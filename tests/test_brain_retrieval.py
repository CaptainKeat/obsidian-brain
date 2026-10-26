"""Exercise production retrieval functions without loading model/service side effects."""
import ast
import re
import threading
import unittest
from pathlib import Path

import brain_memory as bm
import brain_search as bs
import brain_retrieval as br


def engine(rows):
    class Vector:
        def astype(self, _): return self
        def tolist(self): return [1.0, 0.0]
    class Model:
        def encode(self, *args, **kwargs): return Vector()
    class Table:
        def search(self, _):
            self.rows = rows[:]
            return self
        def where(self, clause, prefilter):
            assert prefilter is True
            ids = re.findall(r"'((?:''|[^'])*)'", clause)
            self.rows = [r for r in self.rows if r["id"] in {i.replace("''", "'") for i in ids}]
            return self
        def limit(self, n):
            self.rows = self.rows[:n]
            return self
        def to_list(self): return self.rows
    table = Table()
    env = dict(bs=bs, br=br, bm=bm, Path=Path, model=Model(), _get_table=lambda: table,
               _sql_quote=lambda x: x.replace("'", "''"), _get_reranker=lambda: None,
               _lock=threading.Lock(), _lex_lock=threading.RLock(), LEX_DOCS={}, NOTE_META={},
               _lex={"dirty": True, "flat": [], "bm25": None}, _index_state={},
               DEFAULT_EXCLUDE=[], RERANK=False, EXPAND_DEFAULT=False)
    source = Path(__file__).parents[1] / "rag_indexer.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"chunk_text", "register_lex", "unregister_lex", "_ensure_lex", "do_search"}
    selected = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
    exec(compile(selected, str(source), "exec"), env)
    return env


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.e = engine(self.rows)

    def note(self, path, text, root="vault", chunks=None):
        chunks = chunks or list(self.e["chunk_text"](text))
        docid = root + ":" + path
        self.e["register_lex"](docid, root, path, text, chunks=chunks)
        self.rows.extend(dict(id=docid, root=root, path=path, chunk=c) for c in chunks)

    def search(self, q="recovery", **kwargs):
        return self.e["do_search"](q, **kwargs)

    def test_scope_before_limit(self):
        for i in range(100):
            self.note(f"Other/{i}.md", "recovery common information " * 2)
        self.note("Projects/wanted.md", "recovery scoped project information")
        hits = self.search(include="Projects", candidates=1)
        self.assertEqual([h["path"] for h in hits], ["Projects/wanted.md"])

    def test_drive_identity_preserved(self):
        self.assertIn("drive_d", bs.tokenize("D-drive recovery"))
        self.assertIn("drive_g", bs.tokenize("G drive"))
        self.assertIn("drive_g", bs.tokenize("G:\\Projects"))
        self.assertNotIn("drive_i", bs.tokenize("I need help"))

    def test_unique_notes_fill_k(self):
        self.note("a.md", "recovery first long chunk\n\nrecovery second long chunk",
                  chunks=["recovery first long chunk", "recovery second long chunk"])
        self.note("b.md", "recovery another document")
        self.assertEqual([h["path"] for h in self.search(k=2)], ["a.md", "b.md"])

    def test_same_path_in_two_roots_kept(self):
        self.note("README.md", "recovery information shared")
        self.note("README.md", "recovery information shared", root="projects")
        self.assertEqual({h["root"] for h in self.search(k=2)}, {"vault", "projects"})

    def test_frontmatter_removed_without_reembedding(self):
        text = '---\ntitle: "SECRET METADATA"\nstatus: "observed"\n---\n\nrecovery actual instructions here'
        self.note("a.md", text, chunks=[text])
        self.assertEqual(self.search()[0]["snippet"], "recovery actual instructions here")

    def test_metadata_only_chunks_not_returned(self):
        self.note("a.md", '---\ntitle: "recovery"\n---\n\nrecovery instructions',
                  chunks=['---\ntitle: "recovery"\n---', 'recovery instructions'])
        self.assertEqual(self.search()[0]["snippet"], "recovery instructions")

    def test_current_and_history(self):
        for status in ("stale", "superseded", "rejected", "observed"):
            self.note(status+".md", f'---\nstatus: "{status}"\n---\n\nrecovery instructions {status}')
        self.note("expired.md", '---\nvalid_until: "2020-01-01"\n---\n\nrecovery expired instructions')
        self.assertEqual([h["path"] for h in self.search()], ["observed.md"])
        self.assertEqual(len(self.search(mode="all", k=10)), 5)

    def test_reverse_supersession(self):
        self.note("Projects/old.md", "recovery old instructions here")
        self.note("Projects/new.md", '---\nstatus: "verified"\nevidence: "passed"\nsupersedes: ["Projects/old.md"]\n---\n\nrecovery new instructions here')
        self.assertEqual([h["path"] for h in self.search()], ["Projects/new.md"])
        old = next(h for h in self.search(mode="all") if h["path"].endswith("old.md"))
        self.assertTrue(any("superseded by" in w for w in old["warnings"]))

    def test_unverified_successor_does_not_hide_source(self):
        self.note("old.md", "recovery old instructions here")
        self.note("new.md", '---\nstatus: "proposed"\nsupersedes: ["old.md"]\n---\n\nrecovery proposed instructions')
        self.assertEqual(len(self.search()), 2)

    def test_qualified_link_expansion(self):
        self.note("Start.md", "recovery procedure see [[Projects/Foo#Fix|fix]]")
        self.note("Projects/Foo.md", "Details for the target note without search term")
        hits = self.search(k=1, expand=True)
        self.assertEqual(hits[1]["path"], "Projects/Foo.md")
        self.assertEqual(hits[1]["via"], "link")

    def test_ambiguous_link_not_guessed(self):
        self.note("Start.md", "recovery procedure see [[Foo]]")
        self.note("A/Foo.md", "First unrelated target information")
        self.note("B/Foo.md", "Second unrelated target information")
        hits = self.search(k=1, expand=True)
        self.assertEqual(len(hits), 1)
        self.assertTrue(any("ambiguous" in w for w in hits[0]["warnings"]))

    def test_relative_alias_and_cross_root_resolution(self):
        self.note("A/Foo.md", '---\naliases: ["shortcut"]\n---\n\nA useful target note here')
        self.note("A/Foo.md", "A different project root target", root="projects")
        notes = self.e["NOTE_META"]
        for target in ("./Foo", "../A/Foo", "shortcut"):
            self.assertEqual(br.resolve_link(target, ("vault", "a/start.md"), notes), ("vault", "a/foo.md"))
        self.assertEqual(br.resolve_link("projects:A/Foo", ("vault", "start.md"), notes), ("projects", "a/foo.md"))
        self.assertIsNone(br.resolve_link("../../escape", ("vault", "a/start.md"), notes))

    def test_rerank_failure_reported_and_method_truthful(self):
        self.note("a.md", "recovery instructions for the note")
        hits = self.search("unmatched", rerank=True)
        self.assertEqual(hits[0]["via"], "vector")
        self.assertFalse(hits[0]["reranked"])
        self.assertTrue(any("reranking unavailable" in w for w in hits[0]["warnings"]))

    def test_invalid_inputs(self):
        for kwargs in ({"k": 0}, {"k": 31}, {"mode": "fake"}, {"roots": "unknown"}):
            with self.assertRaises(ValueError): self.search(**kwargs)

    def test_empty_query_and_empty_scope(self):
        self.note("a.md", "recovery instructions for the note")
        self.assertEqual(self.search(""), [])
        self.assertEqual(self.search(include="Missing"), [])

    def test_removed_note_is_removed_from_graph(self):
        self.note("a.md", "recovery instructions for the note")
        self.e["unregister_lex"]("vault:a.md", "a.md")
        self.assertEqual(self.search(), [])
