"""Create an independent local Laya config view; reuse weights without downloads."""
import hashlib
import json
import os
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
config_path = root / "config.json"
config = json.loads(config_path.read_text(encoding="utf-8-sig"))
upstream = Path(config["model_path"])
target = root / "data/models" / config["model_revision"]
if not (upstream / "model.safetensors").is_file():
    raise SystemExit("Missing installed model.safetensors; no download was attempted")
if upstream.resolve() != target.resolve():
    files = ["model.safetensors", "rl_agent_config.json", "encoder/config.json", "tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json"]
    manifest = []
    for relative in files:
        source, dest = upstream / relative, target / relative
        if not source.is_file():
            raise SystemExit("Missing installed model component: " + relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        mode = "existing"
        if not dest.exists():
            if relative == "model.safetensors":
                try:
                    os.link(source, dest)
                    mode = "read-only weights hardlink"
                except OSError:
                    shutil.copy2(source, dest)
                    mode = "weights copy"
            else:
                shutil.copy2(source, dest)
                mode = "independent config copy"
        record = {"file": relative, "source": str(source), "destination": str(dest), "bytes": dest.stat().st_size, "mode": mode}
        if relative != "model.safetensors":
            record["upstream_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest.append(record)
    (root / "data/model-provenance.json").write_text(json.dumps({"revision": config["model_revision"], "source": str(upstream), "files": manifest}, indent=2), encoding="utf-8")
    config["model_path"] = str(target)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
print(json.dumps({"ready": True, "model": str(target), "device": "cpu", "downloaded": False}))
