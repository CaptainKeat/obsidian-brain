# Obsidian Brain

**A local second brain for AI assistants: searchable Markdown memory, guarded
write-back, a visual map and an optional CPU companion.**

Keep knowledge in ordinary notes. Brain combines keyword and semantic search,
reads complete sources, and saves evidence-bearing memories through MCP. The
assistant skill helps resume projects without repeating old work.

| Included | What it provides |
| --- | --- |
| Brain engine · server 3.0.3 / MCP 3.0.0 | BM25 + vectors, distinct-note results, filters, linked-note expansion and optional reranking |
| Memory tools | Typed memories, current/history modes, metadata, hash-guarded revisions/backups and feedback |
| [Assistant skill · 4.0.0](cowork-skill/SKILL.md) | Recall, source verification, checkpoints and evidence rules |
| [Neural Atlas · 0.1](neural-atlas/README.md) | Interactive graph, source reading, Brain search and optional offline CPU triage |
| [Graphify integration](docs/GRAPHIFY.md) | Guidance for the separate upstream graph generator |
| Examples and tests | Synthetic vault, revision demo, graph fixture and regression suites |

New here? Read [how the stack fits together](docs/SECOND-BRAIN.md), then start below.
No personal notes, weights or production databases are included.

## Quick start

Use Python 3.11 or 3.12. In PowerShell:

```powershell
git clone https://github.com/CaptainKeat/obsidian-brain.git
cd obsidian-brain
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe rag_indexer.py
```

The first run downloads an embedding model and indexes `examples/vault` plus
`examples/projects`. Leave the terminal running. In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5180/health
Invoke-RestMethod "http://127.0.0.1:5180/search?q=sample&k=3"
```

Stop with Ctrl+C. On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python`
instead of the Windows executable. Python entry points are portable; `.bat`, `.ps1`
and `.vbs` launchers are Windows-specific.

Try guarded memory revisions without dependencies or model downloads:

```powershell
python examples/revision_demo.py
```

This uses a disposable synthetic vault and checks that stale hashes are rejected.

## Connect an MCP assistant

Start the indexer, then configure your client with the environment's Python and
absolute adapter path. For clients using `mcpServers`:

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "C:/path/to/obsidian-brain/.venv/Scripts/python.exe",
      "args": ["C:/path/to/obsidian-brain/obsidian_brain_mcp.py"],
      "env": {"RAG_URL": "http://127.0.0.1:5180"}
    }
  }
}
```

Replace paths for your machine. Tools are `obsidian_search`, `obsidian_get_note`,
`obsidian_save_memory`, `obsidian_update_note`, `obsidian_record_feedback`,
`obsidian_save_note` and `obsidian_health`. The Windows adapter can try
`start-rag.bat` when down; explicit startup is recommended with custom roots.
Other platforms need explicit startup. No sign-in/startup task is installed.

For Codex, review and install the skill:

```powershell
.\.venv\Scripts\python.exe scripts/sync_skill.py --apply
```

Default target: `~/.codex/skills/obsidian-brain`. Supply repeated `--target <directory>`
for other clients. Files get backups, unrelated files stay intact; omitting
`--apply` only checks drift. Configure your own routine-write authorization; this
skill does not inherit anyone else's personal permissions.

## Configure your own vault

| Variable | Purpose | Default |
| --- | --- | --- |
| `VAULT_PATH` | Markdown vault, read/write | `examples/vault` in checkout |
| `PROJECTS_PATH` | Project docs, read-only through MCP | `examples/projects` |
| `PROJECTS_MAX_DEPTH` | Project scan depth | `2` |
| `DB_PATH` | Generated vector database | `lancedb` in checkout |
| `RAG_PORT` / `RAG_URL` | HTTP port / MCP endpoint | `5180` / `http://127.0.0.1:5180` |
| `EMBED_MODEL` | CPU embedding model | `all-MiniLM-L6-v2` |
| `RAG_TORCH_THREADS` | Embedding CPU thread cap | `4` |
| `RAG_RERANK` | Optional cross-encoder reranking | `0` |
| `RAG_DEFAULT_EXCLUDE` | Comma-separated folder exclusions | empty |

Set matching `VAULT_PATH` and `PROJECTS_PATH` for **both** indexer and MCP adapter.
Shell variables do not automatically transfer to desktop client configuration.
The engine does not load `.env` files automatically.

Vault Markdown is watched live. Project docs refresh at startup or explicit
`POST /reindex`. Health exposes scan timestamps/errors. Changing embedding models
may rebuild the database when dimensions change; use a separate `DB_PATH` to
experiment. `mode=current` hides explicitly stale/expired/superseded notes;
`mode=all` includes history. Read full latest applicable notes before acting.

Upgrading an older checkout? Select a fresh `DB_PATH` once for this release's
chunking fix. Preserve the old index for recovery; ordinary `/reindex` skips
unchanged files and does not regenerate their existing vectors.

## Add the visual companion

```powershell
.\.venv\Scripts\python.exe neural-atlas/configure.py
.\.venv\Scripts\python.exe neural-atlas/atlas.py serve
```

Open <http://127.0.0.1:5190>. This starts a synthetic graph/source demo. The map uses
Python's standard library. Brain search requires the separate indexer; CPU triage
requires a separately installed pinned Laya runtime/model and reports unavailable
weights until configured. See [Atlas setup](neural-atlas/README.md) and
[Graphify integration](docs/GRAPHIFY.md).

## Checks and status

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m unittest discover -s neural-atlas/tests -v
.\.venv\Scripts\python.exe scripts/check_recall.py --report recall-report.json
```

The backend has 44 tests for memory/revision contracts, scope, distinct-note retrieval,
links, history and excerpts. Atlas has 26 temporary-vault, HTTP and supervisor tests
using a fake classifier. The read-only recall checker accepts JSON `--cases`;
keep reports outside indexed roots. [Release notes](CHANGELOG.md) record validation.

This is a source release. Fresh dependency installation, model downloads,
classification quality and another user's sign-in/reboot behavior remain separate
checks. Dependencies are not a locked cross-platform environment.

For connection errors, check `/health`, scan errors, root configuration and the
indexer terminal. Allow slow model startup to finish before retrying. Back up private
generated state separately. Services bind to loopback for trusted local clients;
they are not authenticated public servers. See [SECURITY.md](SECURITY.md).
Original code is [MIT](LICENSE); dependencies/models retain their own licenses.
