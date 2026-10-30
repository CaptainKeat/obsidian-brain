"""Dependency-free note identities, evidence excerpts, and retrieval policy."""
from __future__ import annotations

import posixpath
import re

import brain_memory as bm

VERSION = "3.0.3"


def identity(root, path):
    return root.casefold(), posixpath.normpath(path.replace("\\", "/")).casefold()


def link_targets(text):
    return sorted({m.split("|", 1)[0].split("#", 1)[0].strip()
                   for m in re.findall(r"\[\[([^\]]+)\]\]", text)
                   if m.split("|", 1)[0].split("#", 1)[0].strip()})


def resolve_link(target, source, notes):
    """Resolve same-root paths/relative paths before unique basenames or aliases.

    An explicit vault: or projects: prefix permits cross-root references.
    Ambiguous references return no identity rather than picking an arbitrary note.
    """
    target = target.strip().removeprefix("[[").removesuffix("]]")
    target = target.split("|", 1)[0].split("#", 1)[0].replace("\\", "/")
    root, source_path = source
    if ":" in target:
        prefix, rest = target.split(":", 1)
        if prefix not in {"vault", "projects"}:
            return None
        root, target, source_path = prefix, rest, ""
    target = target.strip()
    if not target:
        return None
    stem = target[:-3] if target.lower().endswith(".md") else target
    # Explicit paths use vault-relative addressing; ./ and ../ are relative.
    if "/" in stem:
        path = (posixpath.join(posixpath.dirname(source_path), stem)
                if stem.startswith(("./", "../")) else stem.lstrip("/"))
        key = identity(root, path + ".md")
        return key if not key[1].startswith("../") and key in notes else None
    local = identity(root, posixpath.join(posixpath.dirname(source_path), stem + ".md"))
    if local in notes:
        return local
    matches = []
    for key, note in notes.items():
        aliases = note["metadata"].get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        if key[0] == root and (posixpath.basename(key[1]) == (stem + ".md").casefold()
                             or stem.casefold() in {str(a).casefold() for a in aliases}):
            matches.append(key)
    return matches[0] if len(matches) == 1 else None


def make_note(root, path, text):
    metadata, body = bm.parse_frontmatter(text)
    return {"root": root, "path": path, "metadata": metadata, "body": body,
            "text": text, "body_start": len(text) - len(body),
            "links": link_targets(body), "warnings": bm.memory_warnings(metadata)}


def body_chunk(chunk, note):
    """Keep vector IDs stable while excluding frontmatter from evidence/search text."""
    start = note["text"].find(chunk)
    if start < 0:
        return ""  # stale indexed text is not evidence for the current file
    cut = max(0, note["body_start"] - start)
    evidence = chunk[cut:].strip()
    # A frontmatter boundary can leave only a Markdown marker (e.g. '#').
    # Keep source/embedding IDs stable, but do not rank it as usable evidence.
    return evidence if re.search(r"[^\W_]", evidence) else ""


def excerpt(text, query, limit=480):
    """Center a bounded excerpt near a query term; preserve nearby heading context."""
    if len(text) <= limit:
        return text.strip()
    terms = set(re.findall(r"[\w-]{2,}", query.casefold()))
    candidates = [m.start() for m in re.finditer(r"[\w-]{2,}", text)
                  if m.group().casefold() in terms]
    offset = max(0, (candidates[0] if candidates else 0) - 100)
    if offset:
        boundary = text.find(" ", offset)
        if boundary != -1:
            offset = boundary + 1
    return ("…" if offset else "") + text[offset:offset + limit].strip() + (
        "…" if offset + limit < len(text) else "")


def note_excerpt(evidence, note, query, limit=480):
    """A heading-only fragment needs source context, not a repeated title."""
    lines = [line.strip() for line in evidence.splitlines() if line.strip()]
    if lines and all(re.match(r"^#{1,6}(?:\s|$)", line) for line in lines):
        evidence = note["body"]
    return excerpt(evidence, query, limit)


def superseded_ids(notes):
    """Derive reverse supersession without rewriting historical notes."""
    result = {}
    for key, note in notes.items():
        meta = note["metadata"]
        if meta.get("status") != "verified" or bm.memory_warnings(meta):
            continue
        links = meta.get("supersedes", [])
        if isinstance(links, str):
            links = [links]
        for link in links:
            old = resolve_link(str(link), key, notes)
            if old is not None and old != key:
                result.setdefault(old, []).append(key)
    return result


def is_current(note, superseded=False):
    meta = note["metadata"]
    return not (superseded or meta.get("status") in {"stale", "superseded", "rejected"}
                or meta.get("superseded_by")
                or any(w.startswith("expired after") for w in bm.memory_warnings(meta)))


def select_notes(ranked, pool, k):
    """Select the highest ranked chunk for each root-qualified document."""
    chosen, seen = [], set()
    for key in ranked:
        item = pool[key]
        doc = identity(item["root"], item["path"])
        if doc in seen:
            continue
        chosen.append(key)
        seen.add(doc)
        if len(chosen) == k:
            break
    return chosen
