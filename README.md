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
| [Assistant skill · 4.2.0](cowork-skill/SKILL.md) | Recall, cross-project learning, source verification and useful write-back |
| [Neural Atlas · 0.1](neural-atlas/README.md) | Interactive graph, source reading, Brain search and optional offline CPU triage |
| [Graphify integration](docs/GRAPHIFY.md) | Guidance for the separate upstream graph generator |
| Examples and tests | Synthetic vault, revision demo, graph fixture and regression suites |

New here? Read [how the stack fits together](docs/SECOND-BRAIN.md), then start below.
No personal notes, weights or production databases are included.

## Cross-project learning: use one shared Brain

The Brain can be a shared knowledge hub for multiple projects and agents. A lesson
learned in one application can be retrieved while working in another repository.
The current project folder does not limit the server's search: it searches the
configured vault and project-document roots.

For example, **Sample Alpha** has a worker-recovery procedure. **Sample Beta** is a
different application with a similar background-worker problem. Beta's agent can
find Alpha's lesson by searching the underlying problem, compare the conditions,
and verify the approach in Beta. The included examples are fictional; they do not
claim a real application was tested.

To enable this across your own projects:

1. Run **one shared Brain instance** for the projects that should share knowledge.
   Point every participating MCP client at the same endpoint, `VAULT_PATH` and
   `PROJECTS_PATH`. The automatic setup generates a matching `mcp-server.json`.
2. Install the [Brain skill](cowork-skill/SKILL.md). Merge
   [these project instructions](templates/PROJECT-AGENTS.md) into each participating
   project's `AGENTS.md`, preserving existing instructions. Automatic setup also
   puts a copy at `<state>/PROJECT-INSTRUCTIONS.md`; it does not edit your repos.
3. Tell the agent your memory-write preference. To enable routine learning, you
   can explicitly instruct it: "During my authorized project work, save useful
   decisions, verified fixes, failed attempts and reusable lessons to the shared
   Brain. Read-only, private and no-save instructions override this preference."
4. Recall the current project's checkpoint, then search the **problem pattern**
   across shared lessons. Remove the current project-name/folder restriction for
   this second search. Read the full lesson and check its evidence, platform,
   version and applicability before using it.
5. Verify the approach in the target project. Save its actual outcome in that
   project's checkpoint, and update the reusable lesson when there is meaningful
   new evidence. Keep project-specific settings out of a universal procedure.

A useful vault layout is:

```text
Cowork/Projects/    # Per-project checkpoints and current state
Cowork/Patterns/    # Reusable procedures
Cowork/Gotchas/     # Failed approaches, pitfalls and retry conditions
Cowork/Examples/    # Worked examples with evidence
```

Folder names are configurable conventions. Typed memory saves use these Cowork
folders by default. Preserve the originating project, evidence/sources,
`applies_when`, limitations and links to relevant checkpoints. Read an existing
lesson before revising it with its current hash rather than adding duplicates.

Ask your MCP-connected assistant to make these calls against the sample vault:

```text
obsidian_search(query="Sample Beta", roots="vault", include="Projects", mode="current")
obsidian_search(query="worker crash recovery persistent pause", roots="vault", include="Patterns,Gotchas,Examples", mode="current")
obsidian_get_note(path="Cowork/Patterns/owned-worker-recovery.md", root="vault")
```

Or, with the example indexer running, try the read-only demonstration:

```powershell
.\.venv\Scripts\python.exe examples/cross_project_demo.py
```

It changes between two disposable caller directories and retrieves the same
Alpha-origin lesson through HTTP, then reads its complete example source. Use
`--url http://127.0.0.1:5180` to select the example indexer. It does not save notes
or evaluate whether an autonomous agent follows the workflow correctly.

Graphify reveals possible connections; Atlas provides a map and review suggestions.
The transfer happens when an agent retrieves, checks and applies the lesson. The
Brain does not automatically ingest every chat or retrain a model. Sharing lessons
does not authorize editing another project's files or starting its services.
**Search filters are not access controls**: use separate vaults/Brain instances for
projects that must not share information.

Already installed? Pull this update, rerun `scripts/sync_skill.py --apply`, and merge
the template into your project instructions. Keep your existing shared MCP entry
and vault; no model replacement, index rebuild or new per-project server is needed.

## Quick start

For the complete Windows background setup—including sign-in startup, crash recovery
and daily semantic graph refresh—follow [Automatic setup](docs/AUTOMATIC-SETUP.md).

Use Python 3.11 or 3.12. In PowerShell:

```powershell
git clone https://github.com/CaptainKeat/obsidian-brain.git
cd obsidian-brain
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu
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
Other platforms need explicit startup. The basic commands do not install tasks;
the optional [Windows installer](docs/AUTOMATIC-SETUP.md) adds them explicitly.

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
.\.venv\Scripts\python.exe examples/cross_project_demo.py
```

The backend and automation suites have 64 tests for memory/revision contracts,
retrieval, incremental refresh, rollback, guarded digest updates and startup ownership.
Atlas has 26 temporary-vault, HTTP and supervisor tests
using a fake classifier. The read-only recall checker accepts JSON `--cases`;
keep reports outside indexed roots. [Release notes](CHANGELOG.md) record validation.

This source release passed a fresh Windows dependency install, default embedding
startup, CPU inference and real scheduled-task checks. First-time Laya weight
download, classification quality and an actual sign-in/reboot remain separate checks.
Core versions are pinned; [verification details](docs/AUTOMATION-VERIFICATION.md)
record the tested scope. Other platforms still need their own checks.

For connection errors, check `/health`, scan errors, root configuration and the
indexer terminal. Allow slow model startup to finish before retrying. Back up private
generated state separately. Services bind to loopback for trusted local clients;
they are not authenticated public servers. See [SECURITY.md](SECURITY.md).
Original code is [MIT](LICENSE); dependencies/models retain their own licenses.

## Native Obsidian graph connections

Typed memories now link to a stable hub for their explicit project label, and to
verified existing vault-note sources. This keeps native graph navigation connected
while preserving Brain metadata identities and historical content. Semantic search
and Graphify remain separate from Obsidian's internal-link graph.

Existing users: read the [safe update and graph repair guide](docs/GRAPH-LINK-REPAIR.md).
It includes a dry-run historical migration, external backups, hash-checked rollback,
client reconnection and validation. No database/model rebuild is required.
For an agent-assisted upgrade, use the guide's
[copyable update and reconciliation prompt](docs/GRAPH-LINK-REPAIR.md#copy-this-prompt-to-your-ai-agent).
