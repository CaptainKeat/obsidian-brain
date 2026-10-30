"""Read-only shared-memory demo against a Brain indexing this repo's sample vault."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, build_opener

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
import brain_memory as bm

LESSON='Cowork/Patterns/owned-worker-recovery.md'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:5180')
    args=parser.parse_args()
    origin=urlsplit(args.url)
    if origin.scheme!='http' or origin.hostname not in ('localhost','127.0.0.1') or origin.username or origin.password or origin.path not in ('','/') or origin.query or origin.fragment:
        parser.error('Use a local Brain HTTP origin')
    opener=build_opener(ProxyHandler({}));previous=Path.cwd();contexts=[]
    with tempfile.TemporaryDirectory() as scratch:
        try:
            for project in ('Sample Alpha','Sample Beta'):
                directory=Path(scratch)/project;directory.mkdir();os.chdir(directory)
                params=urlencode(dict(q='worker crash recovery persistent pause',roots='vault',
                                      include='Patterns,Gotchas,Examples',mode='current',k=5))
                with opener.open(args.url.rstrip('/')+'/search?'+params,timeout=30) as response:
                    hits=json.load(response)
                match=next((h for h in hits if h.get('root')=='vault' and h.get('path')==LESSON),None)
                if match is None:
                    raise RuntimeError('Sample lesson was not found. Start an indexer with the included examples/vault first.')
                note=bm.read_note(LESSON,roots={'vault':REPO/'examples/vault'})
                if match['metadata'].get('project')!='Sample Alpha' or note['metadata'].get('project')!='Sample Alpha':
                    raise RuntimeError('Expected the synthetic lesson to retain its originating project')
                contexts.append(dict(current_project=project,lesson_origin=note['metadata']['project'],
                                     path=match['path'],rank=hits.index(match)+1,source_read=True))
        finally:
            os.chdir(previous)
    print(json.dumps(dict(passed=True,contexts=contexts,
          scope='Synthetic HTTP retrieval and full-source reading from two caller directories; not proof of autonomous agent behavior.'),indent=2))


if __name__=='__main__': main()
