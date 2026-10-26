"""Model-free typed-memory demo using disposable synthetic notes only."""
from pathlib import Path
import json
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import brain_memory as bm

with tempfile.TemporaryDirectory() as temp:
    roots={"vault":Path(temp)/"vault"}
    first=bm.save_memory("Review procedure","Human review is required before delivery.",memory_type="procedure",status="observed",evidence="Synthetic example only",roots=roots)
    second=bm.save_memory("Review procedure","Human review and current version are required before delivery.",memory_type="procedure",status="verified",evidence="Synthetic fixture check",expected_sha256=first["sha256"],roots=roots)
    blocked=False
    try:
        bm.save_memory("Review procedure","Outdated overwrite",memory_type="procedure",expected_sha256=first["sha256"],roots=roots)
    except RuntimeError:
        blocked=True
    assert blocked
    print(json.dumps({"note":second["path"],"status":second["metadata"]["status"],"hash_changed":first["sha256"]!=second["sha256"],"stale_hash_rejected":blocked,"data":"temporary synthetic notes","models_loaded":False},indent=2))
