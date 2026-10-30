"""Create portable, ignored Atlas configuration; no installs or model downloads."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[1]
    parser.add_argument('--vault', type=Path, default=repo / 'examples/vault')
    parser.add_argument('--graph', type=Path, default=repo / 'examples/graph.json')
    parser.add_argument('--model-path', type=Path, help='Existing pinned Laya model directory')
    parser.add_argument('--port', type=int, default=5190)
    args = parser.parse_args()
    if not args.vault.is_dir() or not 1 <= args.port <= 65535:
        parser.error('Vault must exist and port must be between 1 and 65535')
    root = Path(__file__).resolve().parent
    model = args.model_path or root / 'data/models/1c5edc17a7acd8701df6fc341c0d179f1c62c982'
    if args.model_path and not (model / 'model.safetensors').is_file():
        parser.error('Model path must contain model.safetensors')
    config = dict(vault=str(args.vault.resolve()), graph=str(args.graph.resolve()),
                  brain_url='http://127.0.0.1:5180', brain_code=str(repo),
                  python=sys.executable, model_path=str(model.resolve()),
                  model_revision='1c5edc17a7acd8701df6fc341c0d179f1c62c982',
                  port=args.port, threads=2, batch_size=3, batch_interval=20,
                  scan_interval=120, max_note_bytes=1048576)
    target = root / 'config.json'
    # Never replace someone's configured vault/model silently.
    with target.open('x', encoding='utf-8') as out:
        json.dump(config, out, indent=2)
    print('Created config.json. Run prepare_runtime.py before using shared model files.')
    print('Without Laya weights, the map and Brain search work; triage reports unavailable weights.')


if __name__ == '__main__':
    main()
