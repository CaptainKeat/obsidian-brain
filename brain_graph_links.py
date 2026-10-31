"""Portable Obsidian links; Brain metadata identities remain unchanged.

Only exact existing paths, unique basenames, or unique stored titles resolve.
Project hubs group explicit project labels, never guessed topical similarity.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HUB_DIR = "Cowork/Project-Hubs"
START = "<!-- brain-navigation:start -->"
END = "<!-- brain-navigation:end -->"


def project_key(value):
    value = str(value or "").strip()
    if value.startswith("[[") and value.endswith("]]"):
        value = value[2:-2].split("|", 1)[0]
    return value.casefold()


def hub_path(project):
    key = project_key(project)
    slug = re.sub(r"[^\w-]+", "-", key).strip("-")[:60] or "project"
    return f"{HUB_DIR}/{slug}-{hashlib.sha256(key.encode()).hexdigest()[:10]}.md"


def hub_text(project):
    label = str(project).strip()
    if label.startswith("[[") and label.endswith("]]"):
        label = label[2:-2].split("|", 1)[0]
    return ("---\ntitle: " + json.dumps(label + " — project hub", ensure_ascii=False)
            + '\ntype: "project-hub"\nproject_keys: ' + json.dumps([project_key(project)])
            + "\n---\n# " + label + "\n\n"
            + "Navigation hub for notes explicitly assigned to this project label.\n"
            + "Use Backlinks or the local graph to browse linked memories. "
            + "This hub does not assert that historical checkpoint claims remain current.\n")


def visible_spans(text):
    """Keep fenced code, inline code and comments byte-for-byte unchanged."""
    protected = re.compile(r"\A---[^\n]*\n.*?\n---[^\n]*(?:\n|$)|^Revision metadata: [^\n]*|```[^\n]*\n.*?(?:```|\Z)|~~~[^\n]*\n.*?(?:~~~|\Z)|(?P<ticks>`+)[^\n]*?(?P=ticks)|<!--.*?-->", re.S | re.M)
    end = 0
    for match in protected.finditer(text):
        yield end, match.start()
        end = match.end()
    yield end, len(text)


class Catalog:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.paths = {}
        self.names = {}
        self.titles = {}
        self.hubs = {}
        for p in sorted(self.vault.rglob("*.md")):
            if any(part.startswith(".") for part in p.relative_to(self.vault).parts):
                continue
            try:
                if not p.resolve().is_relative_to(self.vault):
                    continue
                text = p.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            rel = p.relative_to(self.vault).as_posix()
            self.paths[rel.casefold()] = rel
            self.names.setdefault(p.stem.casefold(), []).append(rel)
            fm = re.match(r"---\s*\n(.*?)\n---(?:\s*\n|$)", text, re.S)
            if not fm:
                continue
            fields = {}
            for line in fm[1].splitlines():
                if ":" not in line or line.startswith(" "):
                    continue
                k, raw = line.split(":", 1)
                try:
                    fields[k] = json.loads(raw.strip())
                except ValueError:
                    fields[k] = raw.strip().strip("\"'")
            title = fields.get("title")
            if isinstance(title, str):
                self.titles.setdefault(title.casefold(), []).append(rel)
            if fields.get("type") == "project-hub":
                for key in fields.get("project_keys", []):
                    self.hubs.setdefault(project_key(key), []).append(rel)

    def resolve(self, raw, titles=False):
        raw = str(raw).strip().removeprefix("[[").removesuffix("]]")
        raw = raw.split("|", 1)[0].split("#", 1)[0].replace("\\", "/")
        if raw.startswith("vault:"):
            raw = raw[6:]
        elif ":" in raw:
            return None
        if not raw or raw.startswith("/") or ".." in raw.split("/"):
            return None
        path = raw if raw.lower().endswith(".md") else raw + ".md"
        if path.casefold() in self.paths:
            return self.paths[path.casefold()]
        if "/" not in raw:
            matches = self.names.get(raw.removesuffix(".md").casefold(), [])
            if len(matches) == 1:
                return matches[0]
        if titles:
            matches = self.titles.get(raw.casefold(), [])
            if len(matches) == 1:
                return matches[0]
        return None

    def hub(self, project):
        matches = self.hubs.get(project_key(project), [])
        return matches[0] if len(matches) == 1 else None


def repair_links(text, catalog):
    repairs = []
    unresolved = []
    pieces = []
    end = 0
    for start, stop in visible_spans(text):
        pieces.append(text[end:start])
        def replace(match):
            inside = match[1]
            target, sep, label = inside.partition("|")
            destination, anchor, heading = target.partition("#")
            found = catalog.resolve(destination, titles=True)
            if not found:
                if destination.strip():
                    unresolved.append(destination)
                return match[0]
            # Existing valid Obsidian links need no rewrite.
            if not destination.startswith("vault:") and catalog.resolve(destination) == found:
                return match[0]
            path = found[:-3]
            display = label if sep else destination
            repairs.append({"from": destination, "to": found})
            return "[[" + path + ("#" + heading if anchor else "") + "|" + display + "]]"
        pieces.append(re.sub(r"\[\[([^\]]+)\]\]", replace, text[start:stop]))
        end = stop
    pieces.append(text[end:])
    return "".join(pieces), repairs, unresolved


def navigation(text, catalog, *, project=None, sources=(), supersedes=(), self_path=""):
    """Idempotent managed navigation only; metadata/prose identities are retained."""
    text = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", text, flags=re.S)
    text, repairs, unresolved = repair_links(text, catalog)
    links = []
    if project and catalog.hub(project):
        links.append((catalog.hub(project), "Project hub"))
    def refs(value):
        return [value] if isinstance(value, str) else list(value or [])
    source_refs = [raw for raw in refs(sources) if isinstance(raw, str) and
                   (raw.startswith(("vault:", "[[")) or "/" in raw or "\\" in raw)]
    # A bare source filename may describe a repository document, not a vault
    # note. Supersession explicitly denotes a memory relation and is separate.
    for raw in source_refs + refs(supersedes):
        found = catalog.resolve(raw)
        if found and found != self_path and found not in [x[0] for x in links]:
            links.append((found, "Related note"))
    if links:
        text = text.rstrip() + "\n\n" + START + "\n## Brain navigation\n\n" + "\n".join(
            f"- {label}: [[{path[:-3]}]]" for path, label in links) + "\n" + END + "\n"
    return text, repairs, unresolved


def prepare_memory(text, vault, *, project=None, sources=(), supersedes=(), self_path=""):
    # Called only during an authorized save. Creating a hub records the caller's
    # explicit project assignment; it does not infer project identity from prose.
    import brain_memory as bm
    catalog = Catalog(vault)
    if project and project_key(project) and not catalog.hub(project):
        rel = hub_path(project)
        target = bm.resolve_note_path(rel, roots={"vault": Path(vault)}, must_exist=False)
        with bm._note_lock(target):
            if not target.exists():
                bm._atomic_write(target, hub_text(project))
        catalog = Catalog(vault)
    return navigation(text, catalog, project=project, sources=sources,
                      supersedes=supersedes, self_path=self_path)[0]
