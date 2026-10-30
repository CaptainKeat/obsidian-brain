"""Read-only readiness check for a configured, running Brain stack."""
import argparse
import json
from pathlib import Path
import subprocess
import urllib.request
from graph_refresh import read


def check(config):
    checks={}
    try:
        version=subprocess.run([config['codex'],'--version'],capture_output=True,text=True,timeout=15,check=True)
        login=subprocess.run([config['codex'],'login','status'],capture_output=True,text=True,timeout=15)
        checks['codex']=dict(available=True,version=version.stdout.strip(),authenticated=login.returncode==0)
    except Exception as exc: checks['codex']=dict(available=False,authenticated=False,error=str(exc))
    for key,packages in [('python',['mcp','lancedb','sentence-transformers']),('graph_python',['graphifyy']),('atlas_python',[])]:
        code='import importlib.metadata as m,json; print(json.dumps({p:m.version(p) for p in '+repr(packages)+'}))'
        try:
            result=subprocess.run([config[key],'-c',code],capture_output=True,text=True,timeout=30,check=True)
            checks[key]=dict(available=True,versions=json.loads(result.stdout))
        except Exception as exc: checks[key]=dict(available=False,error=str(exc))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for kind,endpoint in [('brain','/health'),('atlas','/api/status')]:
        try:
            with opener.open(f'http://127.0.0.1:{config[kind+"_port"]}'+endpoint,timeout=5) as response:
                value=json.load(response)
            checks[kind]=dict(available=value.get('instance_id')==config['instance_id'],result=value)
        except Exception as exc: checks[kind]=dict(available=False,error=str(exc))
    status=Path(config['state'])/'graph-status.json'
    checks['graph']=read(status) if status.exists() else dict(status='not-yet-run')
    atlas=read(Path(config['state'])/'atlas/config.json')
    checks['laya_weights_present']=(Path(atlas['model_path'])/'model.safetensors').is_file()
    runtime=checks.get('atlas',{}).get('result',{}).get('runtime',{})
    checks['laya_ready']=bool(runtime.get('loaded') and runtime.get('device')=='cpu' and runtime.get('cuda_initialized') is False)
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    result=check(read(parser.parse_args().config));print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['brain']['available'] and result['atlas']['available']
                     and all(result[k]['available'] for k in ['python','graph_python','atlas_python','codex'])
                     and result['codex']['authenticated'] and result['graph']['status'] in {'refreshed','no-op'}
                     and (not result['laya_weights_present'] or result['laya_ready']) else 1)


if __name__=='__main__': main()
