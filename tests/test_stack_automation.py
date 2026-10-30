"""Temporary-vault acceptance checks for graph refresh and portable setup."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import graph_refresh as gr
import setup_stack
import supervise_stack as supervisor


def extraction(batch, config, run):
    return {'nodes':[{'id':p+'::document','label':p,'source_file':p,'type':'document'} for p in batch], 'edges':[]}


def render(fragment,stage,vault,snapshots):
    gr.write(stage/'graph.json',{'nodes':fragment['nodes'],'links':fragment['edges']})
    for name in ('graph.html','GRAPH_REPORT.md','BRAIN_MAP.md'): (stage/name).write_text('generated')
    for name in ('wiki','obsidian'): (stage/name).mkdir()
    return {'nodes':len(fragment['nodes']),'edges':0,'communities':1}


class StackAutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.vault=self.base/'vault';self.vault.mkdir()
        (self.vault/'a.md').write_text('# Alpha\nA useful decision.')
        self.state=self.base/'state'
        self.config={'state':str(self.state),'vault':str(self.vault)}

    def refresh(self,extractor=extraction,renderer=render):
        return gr.refresh(self.config,extractor,renderer)

    def test_unchanged_corpus_does_not_call_semantic_extraction(self):
        self.refresh()
        def forbidden(*a): self.fail('Unchanged corpus triggered extraction')
        self.assertEqual(self.refresh(forbidden)['status'],'no-op')

    def test_content_change_with_same_mtime_is_reextracted(self):
        self.refresh();p=self.vault/'a.md';st=p.stat()
        p.write_text('# Alpha\nChanged decision.')
        import os
        os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
        self.assertEqual(self.refresh()['changed'],1)

    def test_missing_output_is_rebuilt_without_semantic_request(self):
        self.refresh();(self.state/'graph/graphify-out/graph.html').unlink()
        result=self.refresh(lambda *a:self.fail('Output repair triggered extraction'))
        self.assertEqual(result['semantic_extractions'],0)
        self.assertTrue((self.state/'graph/graphify-out/graph.html').is_file())

    def test_deleted_source_is_removed_with_no_semantic_call(self):
        (self.vault/'b.md').write_text('# Bravo\nAnother useful decision.');self.refresh()
        (self.vault/'b.md').unlink()
        result=self.refresh(lambda *a:self.fail('Deletion triggered extraction'))
        self.assertEqual(result['deleted'],1)
        graph=gr.read(self.state/'graph/graphify-out/graph.json')
        self.assertEqual([n['source_file'] for n in graph['nodes']],['a.md'])

    def test_failed_extraction_preserves_previous_graph(self):
        self.refresh();path=self.state/'graph/graphify-out/graph.json';before=path.read_bytes()
        (self.vault/'a.md').write_text('Changed source')
        def fail(*a): raise RuntimeError('Agent unavailable')
        with self.assertRaises(RuntimeError): self.refresh(fail)
        self.assertEqual(path.read_bytes(),before)

    def test_source_edit_during_extraction_blocks_publication(self):
        self.refresh();path=self.state/'graph/graphify-out/graph.json';before=path.read_bytes()
        (self.vault/'a.md').write_text('Changed source')
        def racing(batch,cfg,run):
            result=extraction(batch,cfg,run);(self.vault/'a.md').write_text('Changed again');return result
        with self.assertRaisesRegex(RuntimeError,'Sources changed'): self.refresh(racing)
        self.assertEqual(path.read_bytes(),before)

    def test_invalid_coverage_is_rejected(self):
        with self.assertRaises(ValueError): self.refresh(lambda *a:{'nodes':[],'edges':[]})
        self.assertFalse((self.state/'graph/graphify-out').exists())

    def test_failed_promotion_restores_previous_generation(self):
        output=self.base/'out';output.mkdir();(output/'keep').write_text('original')
        stage=self.base/'stage';stage.mkdir();(stage/'new').write_text('new')
        import os
        def replace(a,b):
            if a == stage: raise OSError('Simulated rename failure')
            os.replace(a,b)
        with self.assertRaises(OSError): gr.promote(stage,output,replace)
        self.assertEqual((output/'keep').read_text(),'original')

    def test_sensitive_private_generated_sources_are_excluded(self):
        (self.vault/'passwords.md').write_text('must not process')
        (self.vault/'private.md').write_text('---\nprivate: true\n---\nDo not process')
        (self.vault/'graphify-out').mkdir();(self.vault/'graphify-out/generated.md').write_text('generated')
        self.assertEqual(set(gr.sources(self.vault)),{'a.md'})

    def test_nested_state_is_rejected(self):
        self.config['state']=str(self.vault/'generated')
        with self.assertRaises(ValueError): self.refresh()

    def test_config_uses_local_paths_and_refuses_overwrite(self):
        projects=self.base/'projects';projects.mkdir()
        args=dict(state=self.state,vault=self.vault,projects=projects,python=sys.executable,codex=sys.executable)
        config=setup_stack.configure(**args)
        self.assertEqual(config['vault'],str(self.vault.resolve()))
        atlas=gr.read(self.state/'atlas/config.json')
        self.assertEqual(atlas['instance_id'],config['instance_id'])
        self.assertTrue((self.state/'atlas/web/index.html').exists())
        mcp=gr.read(self.state/'mcp-server.json')['mcpServers']['obsidian-brain']
        self.assertEqual(mcp['env']['VAULT_PATH'],str(self.vault.resolve()))
        self.assertEqual(mcp['env']['RAG_AUTO_START'],'0')
        self.assertEqual((self.state/'PROJECT-INSTRUCTIONS.md').read_bytes(),
                         (Path(setup_stack.__file__).resolve().parents[1]/'templates/PROJECT-AGENTS.md').read_bytes())
        before=(self.state/'stack.json').read_bytes()
        with self.assertRaises(FileExistsError): setup_stack.configure(**args)
        self.assertEqual((self.state/'stack.json').read_bytes(),before)

    def test_supervisor_refuses_foreign_listener(self):
        self.state.mkdir();config=dict(self.config,instance_id='owned',brain_port=1)
        def status(*a):
            (self.state/'brain.stop').touch();return 'foreign_listener'
        with patch.object(supervisor,'probe',side_effect=status),patch.object(supervisor,'launch') as launch:
            supervisor.run(config,'brain',interval=.1)
            launch.assert_not_called()

    def test_supervisor_terminates_only_its_owned_child_on_stop(self):
        self.state.mkdir();config=dict(self.config,instance_id='owned',brain_port=1)
        from unittest.mock import Mock
        child=Mock(pid=123);child.poll.return_value=None
        def launch(*a): (self.state/'brain.stop').touch();return child
        with patch.object(supervisor,'probe',return_value='missing'),patch.object(supervisor,'launch',side_effect=launch),patch.object(supervisor.subprocess,'run') as stop_tree:
            supervisor.run(config,'brain',interval=.1)
            if supervisor.os.name == 'nt':
                self.assertEqual(stop_tree.call_args.args[0],['taskkill','/PID','123','/T','/F'])
            else: child.terminate.assert_called_once()
        child.kill.assert_not_called()

    def test_confidence_and_dangling_edges_are_rejected(self):
        graph=extraction({'a.md':{}},{},None)
        graph['edges']=[dict(source='missing',target='a.md::document',source_file='a.md',confidence='EXTRACTED',confidence_score=1)]
        with self.assertRaises(ValueError): gr.validate(graph,{'a.md'})

    def test_config_rejects_shared_ports(self):
        projects=self.base/'projects';projects.mkdir()
        with self.assertRaises(ValueError):
            setup_stack.configure(self.state,self.vault,projects,sys.executable,codex=sys.executable,brain_port=1,atlas_port=1)

    def test_digest_preserves_frontmatter_and_rejects_concurrent_edit(self):
        self.config['digest_path']='Maps/brain.md';self.refresh()
        self.assertEqual(gr.publish_digest(self.config,None),'published')
        path=self.vault/'Maps/brain.md';original=path.read_text()
        self.assertIn('status: observed',original)
        self.assertNotIn('Maps/brain.md',gr.sources(self.vault,'Maps/brain.md'))
        expected=gr.digest_snapshot(self.config)
        (self.state/'graph/graphify-out/BRAIN_MAP.md').write_text('changed generated map')
        path.write_text(original+'\nConcurrent editor change')
        with self.assertRaises(RuntimeError): gr.publish_digest(self.config,expected)
        self.assertIn('Concurrent editor change',path.read_text())

    def test_digest_path_escape_is_rejected(self):
        self.config['digest_path']='../outside.md'
        with self.assertRaises(ValueError): gr.digest_snapshot(self.config)

    def test_supervised_mcp_does_not_start_a_second_indexer(self):
        import obsidian_brain_mcp as mcp
        with patch.object(mcp,'_rag_up',return_value=False),patch.dict(mcp.os.environ,{'RAG_AUTO_START':'0'}),patch.object(mcp.subprocess,'Popen') as launch:
            self.assertFalse(mcp._ensure_rag())
            launch.assert_not_called()
