"""Shared lessons keep their origin while remaining available to other projects."""
from pathlib import Path
import unittest
from test_brain_retrieval import engine


class CrossProjectLearningTests(unittest.TestCase):
    def setUp(self):
        self.rows=[];self.e=engine(self.rows)
        vault=Path(__file__).resolve().parents[1]/'examples/vault'
        for file in sorted((vault/'Cowork').rglob('*.md')):
            path=file.relative_to(vault).as_posix();text=file.read_text(encoding='utf-8')
            chunks=list(self.e['chunk_text'](text));doc='vault:'+path
            self.e['register_lex'](doc,'vault',path,text,chunks=chunks)
            self.rows.extend(dict(id=doc,root='vault',path=path,chunk=c) for c in chunks)

    def test_problem_search_finds_another_projects_lesson_with_provenance(self):
        hits=self.e['do_search']('worker crash recovery persistent pause',roots='vault',
                                include='Patterns,Gotchas,Examples',mode='current',k=5)
        lesson=next(h for h in hits if h['path']=='Cowork/Patterns/owned-worker-recovery.md')
        self.assertEqual(lesson['metadata']['project'],'Sample Alpha')
        self.assertIn('persistent pause',lesson['snippet'].lower())

    def test_project_only_scope_does_not_implicitly_broaden(self):
        hits=self.e['do_search']('worker recovery',roots='vault',include='Cowork/Projects',mode='current',k=5)
        self.assertTrue(hits)
        self.assertTrue(all(h['path'].startswith('Cowork/Projects/') for h in hits))
        self.assertNotIn('Cowork/Patterns/owned-worker-recovery.md',{h['path'] for h in hits})
