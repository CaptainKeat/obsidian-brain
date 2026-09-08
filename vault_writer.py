"""
vault_writer.py - Layer 1 (write-back) of the VTuber "Obsidian brain".

Lets the VTuber agent persist notes into the Obsidian vault. For a LOCAL vault
the default is a direct filesystem write (no Obsidian app, no plugin, no key) -
the Layer-3 RAG indexer is watching the vault and will re-index new/changed
notes within ~1.5s automatically.

Optional: if OBSIDIAN_API_KEY is set, writes go through the Obsidian Local REST
API plugin instead (use this only if you want Obsidian-app-mediated writes).

Usage (module):
    from vault_writer import save_note, append_daily
    save_note("The demo user prefers concise answers", "User stated preference on 2026-06-21.",
              tags=["preference", "vtuber"])
    append_daily("Talked about the council architecture.")

Usage (CLI test):
    python vault_writer.py "Some Title" "Body text here"

Env:
    VAULT_PATH         default: examples/vault
    VTUBER_NOTE_DIR    default: VTuber-Memory   (subfolder inside the vault)
    OBSIDIAN_API_KEY   if set -> use Obsidian Local REST API instead of file writes
    OBSIDIAN_HOST      default: http://127.0.0.1:27123
"""
import os
import re
import sys
import datetime
from pathlib import Path

VAULT = Path(os.environ.get("VAULT_PATH", str(Path(__file__).resolve().parent / "examples" / "vault")))
NOTE_DIR = os.environ.get("VTUBER_NOTE_DIR", "VTuber-Memory")
OBSIDIAN_API_KEY = os.environ.get("OBSIDIAN_API_KEY")
OBSIDIAN_HOST = os.environ.get("OBSIDIAN_HOST", "http://127.0.0.1:27123")


def _slug(title, maxlen=60):
    s = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    s = re.sub(r"[\s_]+", "-", s)
    return (s[:maxlen] or "note").strip("-")


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rest_put(rel_path, content):
    """Write via the Obsidian Local REST API plugin."""
    import requests
    url = f"{OBSIDIAN_HOST}/vault/{rel_path.replace(os.sep, '/')}"
    r = requests.put(
        url,
        headers={"Authorization": f"Bearer {OBSIDIAN_API_KEY}",
                 "Content-Type": "text/markdown"},
        data=content.encode("utf-8"),
        timeout=8,
        verify=False,
    )
    r.raise_for_status()
    return url


def save_note(title, content, tags=None, folder=None, source="vtuber"):
    """Create (or append to) a markdown note in the vault.

    If a note with the same slug exists, append a timestamped section rather
    than overwriting - memory accretes instead of being clobbered.
    Returns the absolute path (or REST URL) written.
    """
    folder = folder or NOTE_DIR
    tags = tags or []
    fname = f"{_slug(title)}.md"
    rel = os.path.join(folder, fname)

    if OBSIDIAN_API_KEY:
        body = f"\n\n## {_now()}\n\n{content}\n"
        # REST API has an append endpoint; fall back to PUT full doc
        try:
            import requests
            url = f"{OBSIDIAN_HOST}/vault/{rel.replace(os.sep, '/')}"
            r = requests.post(url, headers={"Authorization": f"Bearer {OBSIDIAN_API_KEY}",
                              "Content-Type": "text/markdown"},
                              data=body.encode("utf-8"), timeout=8, verify=False)
            if r.status_code >= 400:
                _rest_put(rel, _frontmatter(title, tags, source) + body)
            return url
        except Exception as e:
            print(f"[vault_writer] REST write failed ({e}); falling back to file", file=sys.stderr)

    # Direct filesystem write
    target = VAULT / folder / fname
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open("a", encoding="utf-8") as f:
            f.write(f"\n\n## {_now()}\n\n{content}\n")
    else:
        target.write_text(_frontmatter(title, tags, source) + f"\n## {_now()}\n\n{content}\n",
                          encoding="utf-8")
    return str(target)


def _frontmatter(title, tags, source="vtuber"):
    base = list(tags or [])
    if source not in base:
        base.append(source)
    taglist = ", ".join(base)
    return (f"---\n"
            f"title: {title}\n"
            f"created: {_now()}\n"
            f"source: {source}\n"
            f"tags: [{taglist}]\n"
            f"---\n\n"
            f"# {title}\n")


def append_daily(content):
    """Append a line to a single running daily log note."""
    today = datetime.date.today().isoformat()
    return save_note(f"VTuber Daily {today}", content, tags=["daily-log"])


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        src = sys.argv[3] if len(sys.argv) >= 4 else "vtuber"
        path = save_note(sys.argv[1], sys.argv[2], tags=["test"], source=src)
        print(f"wrote: {path}")
    else:
        # self-test
        p = save_note("VTuber Brain Smoke Test",
                      "If you can read this in RAG search, Layer 1 write-back works. "
                      "The demo user prefers concise answers in this synthetic example.",
                      tags=["test", "smoke"])
        print(f"wrote: {p}")
