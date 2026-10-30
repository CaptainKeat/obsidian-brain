# Neural Atlas

A local visual companion for Obsidian Brain. Browse notes and Graphify relationships,
read supporting source text and hashes, search the Brain, and review bounded CPU
triage suggestions. It never writes canonical notes. All browser assets are bundled.

## Start with the synthetic demo

From the repository root, using Python 3.11 or 3.12:

```powershell
python neural-atlas/configure.py
python neural-atlas/atlas.py serve
```

Open <http://127.0.0.1:5190>. Configuration is generated with absolute paths for your
checkout and Python interpreter. `config.json` and `data/` are ignored by Git.
The map needs no third-party Python packages. Brain search needs the separate indexer
running at port 5180. Without model weights, triage reports unavailable weights in
status; source reading and graph browsing remain available. Stop with Ctrl+C.

To use your own vault, pass paths when creating the configuration:

```powershell
python neural-atlas/configure.py --vault "C:/Notes/MyVault" --graph "C:/BrainMap/graphify-out/graph.json"
```

The helper refuses to overwrite an existing configuration. Edit `config.json` to
change an existing setup, including `brain_url`. Keep Atlas and Brain pointed at
the same vault. Graph input is optional; a missing graph is reported in status.

## Optional Laya CPU triage

The implementation targets `laya==0.3.6` and the
[Laya model](https://huggingface.co/convaiinnovations/laya/tree/1c5edc17a7acd8701df6fc341c0d179f1c62c982)
revision `1c5edc17a7acd8701df6fc341c0d179f1c62c982`. Newer Laya APIs and models are
not assumed compatible. Model weights and their upstream license are separate.

Install optional dependencies in a dedicated environment. A CPU-only PyTorch
install can be selected using [PyTorch's instructions](https://pytorch.org/get-started/locally/).
No packages or weights are installed by `configure.py`, `prepare_runtime.py` or Atlas.

```powershell
python -m pip install -r neural-atlas/requirements.txt
```

Obtain that exact model revision separately. When creating the config, add
`--model-path "C:/Models/laya-pinned"`. Then run:

```powershell
python neural-atlas/prepare_runtime.py
python neural-atlas/atlas.py serve
```

`prepare_runtime.py` creates an independent tokenizer/config view under `data/models`,
hardlinking weights when possible or copying them. Do this before sharing a model
directory with another app: Laya may normalize tokenizer configuration while loading.
Keep that local directory; inference is offline. Failed jobs remain visible and can
be retried from the inbox after the model is configured.

Inference uses CPU explicitly, two Torch threads, one interop thread, one request at
a time, three notes per cycle and a 260-token excerpt. Results are suggestions with
uncalibrated scores. Source edits invalidate previous results; raw revisions and
review history remain in `data/atlas.sqlite3`. That database contains copied source
text and is private. Keep it when retaining history; never publish it.

## Controls and recovery

The interface supports pause/resume, rescan, graph filters and neighborhoods, source
reading, Brain search, and copying up to eight source-hashed excerpts for assistant
review. Accepting/dismissing a suggestion updates only derived Atlas review state.
Canonical changes require the Brain's existing writer and fresh source hashes.

Windows PowerShell 7 users can run `Start-Atlas.ps1` or double-click `Start-Atlas.vbs`.
`Stop-Atlas.ps1` stops only this companion and retains paused state and evidence.
The scripts use PowerShell 7's `-NoProxy`; use the Python command for other shells.

An optional `atlas_supervisor.py --root <absolute-atlas-directory>` can be registered
with your own user-session scheduler. It polls every 30 seconds, reuses healthy
workers and backs off after failures. Saved pause/intentional Stop prevents restart.
The [optional Windows stack installer](../docs/AUTOMATIC-SETUP.md) installs per-user
sign-in tasks, worker recovery and daily graph refresh. Test your own restart/sign-in
behavior before relying on it; do not register it using someone else's paths.

## Verification and limits

```powershell
python -B -m unittest discover -s neural-atlas/tests -v
```

The 26 existing tests use temporary synthetic vaults and a fake classifier. They
exercise source revisions, stale-result rejection, path boundaries, API controls,
queue recovery and supervisor behavior. They do not evaluate classification accuracy
or prove a fresh model/dependency install. Windows is the primary launcher platform;
the Python entry point avoids those launcher dependencies.

The overview is bounded to 300 nodes and the accessible list to 60. Only admitted
vault Markdown enters the local map. Sensitive-name and frontmatter exclusions
help limit ingestion, but are not a complete private-data classifier. Graphify
relationships are discovery evidence; inspect current full sources before acting.
