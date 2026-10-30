"""
obsidian_brain_mcp.py - MCP server exposing the user's Obsidian RAG brain to ANY
Cowork / Claude Desktop session.

Configure this stdio adapter in an MCP client to expose the tools below.
It wraps the local RAG indexer
on :5180 (hybrid keyword+vector, indexes the configured vault + project docs).

Self-healing: if the RAG server is down (e.g. it crashed or the startup script
didn't run), this MCP launches start-rag.bat itself and waits for /health.

Tools:
  - obsidian_search(query, k, include, exclude, roots, expand, rerank) -> hybrid recall
  - obsidian_get_note(path, root, section, max_chars)            -> safe full-note/section read
  - obsidian_save_memory(...)                                    -> typed, evidence-bearing memory
  - obsidian_update_note(...)                                    -> append or hash-guarded replacement
  - obsidian_record_feedback(...)                                -> stale/wrong/helpful retrieval feedback
  - obsidian_save_note(title, body)                               -> legacy free-form write-back
  - obsidian_health()                                             -> is the brain up + what's indexed
"""
import json
import os
import subprocess
import sys
import time

import requests
from mcp.server.fastmcp import FastMCP

import brain_memory

RAG_URL = os.environ.get("RAG_URL", "http://127.0.0.1:5180").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
START_BAT = os.path.join(HERE, "start-rag.bat")

mcp = FastMCP("obsidian-brain")


def _rag_up(timeout=3):
    try:
        response = requests.get(f"{RAG_URL}/health", timeout=timeout)
        response.raise_for_status()
        return response.json().get("status") == "ok"
    except Exception:
        return False


def _ensure_rag(wait=60):
    """If the RAG server is down, launch start-rag.bat without a visible console
    (output goes to rag.log) and poll /health until it's up or `wait` seconds pass.
    Start the indexer explicitly when using custom root configuration."""
    if _rag_up():
        return True
    if os.environ.get("RAG_AUTO_START", "1") == "0":
        return False  # A configured external supervisor owns startup/recovery.
    if os.name != "nt":
        return False  # Start the indexer explicitly on macOS/Linux.
    try:
        subprocess.Popen(
            ["cmd", "/c", START_BAT],
            cwd=HERE,
            # DETACHED_PROCESS can still make console children open in Windows
            # Terminal. CREATE_NO_WINDOW keeps the whole batch/Python chain hidden.
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        if _rag_up():
            return True
        time.sleep(1.5)
    return _rag_up()


def _memory_tag(path, root):
    try:
        metadata = brain_memory.compact_metadata(brain_memory.note_info(path, root))
        return f" [{metadata}]" if metadata else ""
    except Exception:
        # Project roots may move or a file may disappear between search and read.
        return ""


@mcp.tool()
def obsidian_search(query: str, k: int = 6, include: str = "", exclude: str = "VTuber-Memory",
                    roots: str = "", expand: bool = False, rerank: bool = False,
                    mode: str = "current") -> str:
    """Search the configured Markdown vault and project documents.
    Recall notes, decisions, project context, past setups, gotchas, and patterns - anything
    the user has written down. Hybrid keyword + vector search; each hit shows its source path,
    retrieval path, and available type/status/freshness metadata.

    Args:
        query: what to look up (natural language; exact terms/acronyms work too).
        k: how many distinct notes to return (1-30, default 6); expansion adds at most k links.
        include: comma-separated folders to restrict to (e.g. "Patterns,Gotchas,Projects").
        exclude: comma-separated folders to skip (default "VTuber-Memory", the VTuber's chatter).
        roots: comma-separated index roots to search. Valid roots are "vault" and "projects". Empty searches both.
        expand: also pull in notes linked via [[wikilinks]] from the top hits (graph expansion).
        rerank: opt into CPU cross-encoder reranking for a difficult, high-value lookup.
        mode: current hides explicitly stale/expired/superseded notes; all includes history.
            Current does not mean verified. Read warnings and sources.
    """
    params = {"q": query, "k": k, "mode": mode}
    if include:
        params["include"] = include
    if exclude:
        params["exclude"] = exclude
    if roots:
        params["roots"] = roots
    if expand:
        params["expand"] = 1
    if rerank:
        params["rerank"] = 1
    if not _rag_up():
        if not _ensure_rag():
            return (f"RAG brain unreachable at {RAG_URL} and auto-start failed. "
                    f"Check rag.log in {HERE}.")
    try:
        r = requests.get(f"{RAG_URL}/search", params=params, timeout=20)
        r.raise_for_status()
        hits = r.json()
    except Exception as e:
        return f"RAG brain errored at {RAG_URL} ({e}). Check rag.log in {HERE}."
    if not hits:
        return "No matching notes found."
    out = []
    for h in hits:
        root = h.get("root", "?")
        path = h.get("path", "?")
        via = h.get("via", "")
        snip = (h.get("snippet", "") or "").strip().replace("\n", " ")
        via_tag = f" ({via}; reranked={h.get('reranked', False)})" if via else ""
        warnings = "; ".join(h.get("warnings", []))
        if warnings:
            snip += f"\n  Warnings: {warnings}"
        out.append(f"[{root}] {path}{via_tag}{_memory_tag(path, root)}\n  {snip}")
    return "\n\n".join(out)


@mcp.tool()
def obsidian_get_note(path: str, root: str = "vault", section: str = "",
                      max_chars: int = 16000) -> str:
    """Read a complete note or one heading after search has identified it.

    The result includes frontmatter, SHA-256, modification time, freshness/status
    warnings, and content. Use the returned SHA-256 for safe replacements.

    Args:
        path: RAG-relative Markdown path exactly as returned by obsidian_search.
        root: "vault" or "projects", matching the search result.
        section: optional Markdown heading to extract.
        max_chars: maximum content characters returned (500-100000).
    """
    try:
        result = brain_memory.read_note(path, root=root, section=section, max_chars=max_chars)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Read failed: {e}"


@mcp.tool()
def obsidian_save_memory(title: str, body: str, memory_type: str,
                         status: str | None = None, confidence: str | None = None,
                         project: str | None = None, evidence: str | None = None,
                         applies_when: str | None = None, sources: str | None = None, tags: str | None = None,
                         valid_until: str | None = None, supersedes: str | None = None,
                         expected_sha256: str = "") -> str:
    """Save a typed durable memory with provenance instead of raw conversation.

    Verified memories require evidence or a source. Files are routed under
    Cowork/{Patterns,Gotchas,Sessions,Examples,...} and auto-indexed.

    Args:
        title: concise reusable memory title.
        body: distilled lesson, decision, fact, or worked example.
        memory_type: fact, project-state, decision, procedure, incident,
            worked-example, hypothesis, preference, or gotcha.
        status: proposed, observed, verified, stale, superseded, or rejected.
        confidence: low, medium, or high.
        project: optional project name.
        evidence: test result or observation supporting this memory.
        applies_when: conditions under which the lesson transfers.
        sources: comma-separated source paths, commands, URLs, or note links.
        tags: comma-separated tags.
        valid_until: optional ISO date/time after which re-verification is required.
        supersedes: comma-separated older note links or paths this replaces.
        expected_sha256: required when the title already exists; read the note first.
            Omitted/null optional fields preserve existing metadata; empty values clear it.
            New memories default to verified and require evidence; revisions need fresh
            evidence when verified. Revision history and a backup are retained.
    """
    split = lambda value: None if value is None else [part.strip() for part in value.split(",") if part.strip()]
    try:
        result = brain_memory.save_memory(
            title,
            body,
            memory_type=memory_type,
            status=status,
            confidence=confidence,
            project=project,
            evidence=evidence,
            applies_when=applies_when,
            sources=split(sources),
            tags=split(tags),
            valid_until=valid_until,
            supersedes=split(supersedes),
            expected_sha256=expected_sha256,
        )
        return "Saved typed memory:\n" + json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Typed memory save failed: {e}"


@mcp.tool()
def obsidian_update_note(path: str, body: str, root: str = "vault",
                         mode: str = "append", heading: str = "Update",
                         expected_sha256: str = "") -> str:
    """Safely update a note previously read with obsidian_get_note.

    Append is the default. replace_body preserves frontmatter, requires the
    previously returned SHA-256, rejects stale writes, and creates a .bak file.
    Project-index documents are intentionally read-only through this tool.

    Args:
        path: RAG-relative Markdown path.
        body: content to append or the complete replacement Markdown body.
        root: must be "vault" for writes.
        mode: append or replace_body.
        heading: heading used for an appended observation.
        expected_sha256: optional for append; mandatory for replace_body.
    """
    try:
        result = brain_memory.update_note(
            path,
            body,
            root=root,
            mode=mode,
            heading=heading,
            expected_sha256=expected_sha256,
        )
        return "Updated note:\n" + json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Update failed: {e}"


@mcp.tool()
def obsidian_record_feedback(path: str, outcome: str, detail: str,
                             query: str = "") -> str:
    """Record whether a retrieved memory was helpful, stale, wrong, missing, or contradictory.

    This creates an append-only feedback trail for retrieval evaluation and later
    consolidation; it does not silently rewrite the target note.

    Args:
        path: note path involved, or "(missing)" when retrieval found nothing.
        outcome: helpful, stale, wrong, missing, or contradictory.
        detail: concrete correction or explanation.
        query: optional original search query.
    """
    try:
        result = brain_memory.record_feedback(path, outcome, detail, query=query)
        return "Recorded brain feedback:\n" + json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Feedback save failed: {e}"


@mcp.tool()
def obsidian_save_note(title: str, body: str) -> str:
    """Legacy free-form write into the configured memory folder.

    Prefer obsidian_save_memory for durable facts, procedures, decisions, incidents,
    worked examples, and gotchas because it records status, evidence, and applicability.
    This compatibility tool remains useful for a quick unstructured session note.

    Args:
        title: short note title.
        body: the note content (Markdown is allowed).
    """
    try:
        sys.path.insert(0, HERE)
        import vault_writer
        path = vault_writer.save_note(title, body, tags=["cowork"], folder="Cowork", source="cowork")
        return f"Saved and queued for indexing: {path}"
    except Exception as e:
        return f"Save failed: {e}"


@mcp.tool()
def obsidian_health() -> str:
    """Check whether the RAG brain is up and how much is indexed. If it's down,
    this attempts to auto-start it first."""
    started = ""
    if not _rag_up():
        if _ensure_rag():
            started = " (was down - auto-started it)"
        else:
            return (f"down - auto-start failed. Check rag.log in {HERE} "
                    f"or run start-rag.bat manually.")
    try:
        h = requests.get(f"{RAG_URL}/health", timeout=5).json()
        return (f"up{started}: {h.get('by_root')} | {h.get('chunks')} chunks | model {h.get('model')} "
                f"| rerank={h.get('rerank')} | excluded={h.get('default_exclude')} "
                f"| mcp_version=3.0.0 | server_version={h.get('version', 'unknown')} "
                f"| capabilities={h.get('capabilities', [])} | index_state={h.get('index_state', {})}")
    except Exception as e:
        return f"down ({e})"


if __name__ == "__main__":
    mcp.run()
