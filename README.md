# Obsidian Brain Engine

A local Markdown memory engine: hybrid keyword/vector search, linked-note expansion,
optional reranking, full-note retrieval, typed memory writes, and hash-guarded updates.
An MCP adapter exposes these operations to a compatible client.

This release contains reusable Python source and a tiny synthetic vault. It does
not contain a personal vault, index database, session history or voice samples.

## Setup

Use Python 3.11 or 3.12 in a virtual environment:

```sh
python -m venv .venv
# Activate the environment using your shell's activation command.
python -m pip install -r requirements.txt
python rag_indexer.py
```

The indexer binds to `127.0.0.1:5180`. Its initial embedding model may download from
the model provider. Defaults index only `examples/vault` and `examples/projects`.
Set `VAULT_PATH` and `PROJECTS_PATH` to opt into your own directories. `DB_PATH`
selects the local database folder; `RAG_PORT` selects the HTTP port. Do not point
this service at a sensitive collection until you understand the client's access.

Configure an MCP client to execute your virtual environment's Python with the
absolute path to `obsidian_brain_mcp.py` as its argument. The adapter uses `RAG_URL`
(default `http://127.0.0.1:5180`). On Windows it can launch `start-rag.bat` when the
indexer is unavailable; on other systems start the indexer yourself first.
The source release does not install a startup task or desktop extension.

## Test the note layer without models

`python -m unittest discover -s tests -v`

These tests use temporary synthetic files and exercise path boundaries, typed
memory metadata, section retrieval, update hashes and feedback. They do not require
the embedding stack. `brain_search.py` contains dependency-free ranking helpers.

## Status

Community-maintained source extraction. The note tests and syntax checks are part
of release validation; the full model/indexing/MCP runtime is not freshly validated.
HTTP endpoints are intended for local trusted clients and have no public-server
authentication layer. Do not expose the indexer over the network.

Original code: MIT. Python dependencies and model weights retain their own licenses.
