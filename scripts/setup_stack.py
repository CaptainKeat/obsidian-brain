"""Configure a per-user Brain, Atlas and daily semantic Graphify installation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


def configure(state, vault, projects, python, graph_python=None, atlas_python=None,
              codex=None, brain_port=5180, atlas_port=5190, model_path=None,digest_path=None):
    repo=Path(__file__).resolve().parents[1]
    state,vault,projects=map(lambda p:Path(p).resolve(),(state,vault,projects))
    if not vault.is_dir() or not projects.is_dir():
        raise ValueError('Vault and project directories must already exist')
    for source in (vault,projects):
        if state == source or state.is_relative_to(source) or source.is_relative_to(state):
            raise ValueError('State must be separate from both indexed source roots')
    if brain_port == atlas_port or any(not 1 <= p <= 65535 for p in (brain_port,atlas_port)):
        raise ValueError('Choose distinct ports between 1 and 65535')
    if not codex or not Path(codex).is_file():
        raise ValueError('Locate an installed Codex CLI executable with --codex')
    if digest_path:
        sys.path.insert(0,str(repo))
        import brain_memory as bm
        bm.resolve_note_path(digest_path,'vault',{'vault':vault},must_exist=False)
    target=state/'stack.json'
    if target.exists():
        raise FileExistsError('Existing stack.json preserved; edit it explicitly instead')
    state.mkdir(parents=True,exist_ok=True)
    atlas=state/'atlas';atlas.mkdir(exist_ok=True)
    for name in ['atlas.py','atlas_supervisor.py','prepare_runtime.py']:
        shutil.copy2(repo/'neural-atlas'/name,atlas/name)
    shutil.copytree(repo/'neural-atlas/web',atlas/'web',dirs_exist_ok=True)
    identity=hashlib.sha256(str(target).encode()).hexdigest()[:12]
    config=dict(repo=str(repo),state=str(state),vault=str(vault),projects=str(projects),
                python=str(Path(python).resolve()),graph_python=str(Path(graph_python or python).resolve()),
                atlas_python=str(Path(atlas_python or python).resolve()),codex=str(Path(codex).resolve()),
                brain_port=brain_port,atlas_port=atlas_port,instance_id=identity,
                embed_model='all-MiniLM-L6-v2',hf_home=str(state/'model-cache'),threads=2,graph_timeout_seconds=900,digest_path=digest_path)
    atlas_config=dict(vault=str(vault),graph=str(state/'graph/graphify-out/graph.json'),
                      brain_url=f'http://127.0.0.1:{brain_port}',brain_code=str(repo),
                      python=config['atlas_python'],model_path=str(Path(model_path).resolve()) if model_path else str(atlas/'data/models/unconfigured'),
                      model_revision='1c5edc17a7acd8701df6fc341c0d179f1c62c982',instance_id=identity,
                      port=atlas_port,threads=2,batch_size=3,batch_interval=20,scan_interval=120,max_note_bytes=1048576)
    (atlas/'config.json').write_text(json.dumps(atlas_config,indent=2),encoding='utf-8')
    with target.open('x',encoding='utf-8') as out: json.dump(config,out,indent=2)
    mcp={'mcpServers':{'obsidian-brain':{
        'command':config['python'],'args':[str(repo/'obsidian_brain_mcp.py')],
        'env':{'VAULT_PATH':str(vault),'PROJECTS_PATH':str(projects),
               'RAG_URL':f'http://127.0.0.1:{brain_port}','RAG_AUTO_START':'0'}}}}
    (state/'mcp-server.json').write_text(json.dumps(mcp,indent=2),encoding='utf-8')
    if model_path:
        import subprocess
        subprocess.run([config['atlas_python'],str(atlas/'prepare_runtime.py')],check=True)
    return config


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','vault','projects'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--python',default=sys.executable)
    p.add_argument('--graph-python');p.add_argument('--atlas-python')
    p.add_argument('--codex',default=shutil.which('codex'))
    p.add_argument('--brain-port',type=int,default=5180);p.add_argument('--atlas-port',type=int,default=5190)
    p.add_argument('--model-path',type=Path)
    p.add_argument('--digest-path',help='Optional reserved generated Markdown path relative to the vault')
    config=configure(**vars(p.parse_args()))
    print(json.dumps(dict(config=str(Path(config['state'])/'stack.json'),instance_id=config['instance_id'])))


if __name__ == '__main__': main()
