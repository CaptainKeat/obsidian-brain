# Obsidian Brain Engine

**Give an AI client searchable, structured memory over local Markdown.**

Obsidian Brain combines keyword and semantic search with linked-note retrieval and controlled write-back. A local HTTP indexer handles search; an MCP adapter exposes search, note reading and memory operations to compatible clients.

| Data format | Search | Client interface | License |
| --- | --- | --- | --- |
| Markdown files | BM25 + embeddings; optional reranking | MCP + local HTTP | MIT |

## What it does

- Searches a Markdown vault and a separate collection of project documents.
- Combines keyword and vector results, with folder filters and optional linked-note expansion.
- Reads complete notes or selected sections with source metadata.
- Saves typed memories such as facts, decisions, procedures and project state.
- Supports append operations, hash-guarded replacement and retrieval feedback.

The repository includes a small **synthetic demo vault**. You can inspect the workflow before connecting your own notes.

## Requirements

- [Python](https://www.python.org/downloads/) 3.11 or 3.12 for the documented dependency environment.
- Disk space for the local database and embedding-model cache.
- Internet access for installing dependencies and the initial model download.
- An MCP-compatible client if you want to use the adapter.

The default embedding model is `all-MiniLM-L6-v2`. The indexer is configured for CPU use. Full dependency/model startup has not been freshly integration-tested for this release.

## Install and start the example index

With Python 3.12 installed, run these commands in PowerShell:

```powershell
git clone https://github.com/CaptainKeat/obsidian-brain.git
cd obsidian-brain
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe rag_indexer.py
```

The first startup may download the embedding model. Leave this terminal running. In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5180/health
Invoke-RestMethod "http://127.0.0.1:5180/search?q=sample&k=3"
```

The first request reports indexer health; the second searches the included examples. Stop the indexer with **Ctrl+C**.

On macOS/Linux, create the environment with `python3 -m venv .venv` and use `.venv/bin/python` for the installation and launch commands.

## Connect an MCP client

Point the client's stdio server configuration at the virtual environment's Python and the absolute path to `obsidian_brain_mcp.py`. For clients that use an `mcpServers` configuration object, the shape is:

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

Replace both example paths with your checkout location; the exact configuration format depends on the client. On Windows the adapter can launch `start-rag.bat` if the indexer is down. On other platforms, start the indexer separately first.

## Configure your own data

| Variable | Purpose | Default |
| --- | --- | --- |
| `VAULT_PATH` | Markdown vault to index and read/write | `examples/vault` in this repo |
| `PROJECTS_PATH` | Separate project-document root | `examples/projects` in this repo |
| `PROJECTS_MAX_DEPTH` | Project scan depth | `2` |
| `DB_PATH` | Local vector database directory | `lancedb` in this repo |
| `RAG_PORT` / `RAG_URL` | Indexer port / adapter endpoint | `5180` / `http://127.0.0.1:5180` |
| `EMBED_MODEL` | Embedding model | `all-MiniLM-L6-v2` |
| `RAG_RERANK` | Enable optional reranking | `0` |

Set matching `VAULT_PATH` and `PROJECTS_PATH` values for **both** the indexer and MCP adapter. The search index and note reader must point to the same collections. Supply environment variables through your shell or client configuration; the engine does not automatically load a `.env` file.

## Tests, troubleshooting and status

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The five note-layer tests passed using temporary synthetic files. They cover path escapes, section retrieval, typed metadata, update hashes and append-only feedback. They can also run without the embedding dependencies using a standard Python interpreter.

- **Connection refused:** start the indexer and check its terminal output and `/health` endpoint.
- **No search results:** check the configured roots and wait for initial indexing to finish.
- **Dependency installation fails:** confirm the Python version and use an isolated environment.
- **Search and note reads disagree:** confirm both processes use the same root variables.

The HTTP service is for trusted local clients and binds to loopback. It has no public-server authentication layer. See [SECURITY.md](SECURITY.md) before using private data.

Contributions are welcome: reproducible dependency installs, indexer integration tests, cross-platform startup and better documentation. Original source is [MIT licensed](LICENSE); dependencies and model weights retain their own licenses.
