"""Low-cost supervisor; launches only its configured Brain or Atlas."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
from graph_refresh import lock, read, write


def probe(config, kind):
    endpoint='/health' if kind == 'brain' else '/api/status'
    url=f'http://127.0.0.1:{config[kind+"_port"]}'+endpoint
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url,timeout=3) as response: data=json.load(response)
        return 'healthy' if data.get('instance_id') == config['instance_id'] else 'foreign_listener'
    except urllib.error.HTTPError: return 'foreign_listener'
    except urllib.error.URLError as exc:
        reason=exc.reason
        if isinstance(reason,ConnectionRefusedError) or getattr(reason,'winerror',None)==10061 or getattr(reason,'errno',None) in {61,111,10061}:
            return 'missing'
        return 'unreachable'
    except (OSError,ValueError): return 'unreachable'


def launch(config, kind):
    state,repo=Path(config['state']),Path(config['repo']);env=os.environ.copy()
    if kind == 'brain':
        env.update(VAULT_PATH=config['vault'],PROJECTS_PATH=config['projects'],DB_PATH=str(state/'lancedb'),
                   RAG_PORT=str(config['brain_port']),RAG_INSTANCE_ID=config['instance_id'],
                   EMBED_MODEL=config['embed_model'],RAG_TORCH_THREADS=str(config['threads']))
        if config.get('hf_home'): env['HF_HOME']=config['hf_home']
        command=[config['python'],'-B','-u',str(repo/'rag_indexer.py')]
    else:
        command=[config['atlas_python'],'-B','-u',str(state/'atlas/atlas.py'),'serve','--root',str(state/'atlas')]
    with (state/(kind+'.log')).open('ab') as log:
        return subprocess.Popen(command,env=env,cwd=repo,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)


def run(config,kind,interval=30,backoff=120):
    state=Path(config['state']);owned=None;next_launch=0;stop=state/(kind+'.stop')
    with lock(state/(kind+'-supervisor.lock')):
        try:
            while not stop.exists():
                status=probe(config,kind)
                if status == 'missing' and (owned is None or owned.poll() is not None) and time.monotonic() >= next_launch:
                    paused=False
                    if kind=='atlas' and (state/'atlas/data/atlas.sqlite3').exists():
                        import sqlite3
                        with sqlite3.connect((state/'atlas/data/atlas.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
                            row=db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()
                            paused=bool(row and json.loads(row[0]))
                    if paused: status='paused_restart_suppressed'
                    else:
                        owned=launch(config,kind);status='starting';next_launch=time.monotonic()+backoff
                write(state/(kind+'-status.json'),dict(status=status,supervisor_pid=os.getpid(),
                      owned_child_pid=owned.pid if owned and owned.poll() is None else None,instance_id=config['instance_id']))
                for _ in range(max(1,int(interval*10))):
                    if stop.exists(): break
                    time.sleep(.1)
        finally:
            # The process handle identifies exactly the child launched here.
            if owned and owned.poll() is None:
                if os.name == 'nt':
                    # A Windows venv Python launcher can own the actual interpreter
                    # as a descendant. End only this retained launcher's tree.
                    subprocess.run(['taskkill','/PID',str(owned.pid),'/T','/F'],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    owned.terminate()
                try: owned.wait(timeout=15)
                except subprocess.TimeoutExpired: owned.kill();owned.wait(timeout=5)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--kind',choices=['brain','atlas'],required=True)
    p.add_argument('--interval',type=float,default=30);p.add_argument('--backoff',type=float,default=120)
    a=p.parse_args();run(read(a.config),a.kind,a.interval,a.backoff)


if __name__=='__main__': main()
