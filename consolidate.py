"""consolidate.py - periodic consolidation / health pass over the Obsidian vault (#5).

Report-only by default. Flags near-duplicate notes, supersede/stale markers, and old
notes, then writes a review report into Sessions/. It NEVER deletes or merges - it
produces a checklist for the user to review. Runs on the machine where the vault lives:

    python consolidate.py                 # -> Sessions/brain-consolidation-<date>.md
    python consolidate.py --days 60       # change the "stale" threshold
    python consolidate.py --vault PATH    # override the vault location

Dependency-light: stdlib + brain_search.py (no torch / no model load).
"""
import os
import re
import argparse
import datetime
from pathlib import Path

import brain_search as bs

DEFAULT_VAULT = os.environ.get("VAULT_PATH", str(Path(__file__).resolve().parent / "examples" / "vault"))
SKIP_DIRS = {".obsidian", ".trash", ".git"}
SKIP_REL_PREFIX = ("VTuber-Memory/daily", "Sessions/brain-consolidation-")
SUPERSEDE_RE = re.compile(r"(supersed|out of date|outdated|deprecat|retired|no longer)", re.I)


def read_notes(vault):
    notes = []
    for dp, dn, fn in os.walk(vault):
        dn[:] = [d for d in dn if d.lower() not in SKIP_DIRS]
        for f in fn:
            if not f.lower().endswith(".md"):
                continue
            fp = os.path.join(dp, f)
            rel = os.path.relpath(fp, vault).replace(os.sep, "/")
            if any(rel.startswith(p) for p in SKIP_REL_PREFIX):
                continue
            try:
                text = Path(fp).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            notes.append({"rel": rel, "mtime": os.path.getmtime(fp),
                          "text": text, "tokens": set(bs.tokenize(text))})
    return notes


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_near_dups(notes, thr):
    out = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            s = jaccard(notes[i]["tokens"], notes[j]["tokens"])
            if s >= thr:
                out.append((s, notes[i]["rel"], notes[j]["rel"]))
    out.sort(reverse=True)
    return out


def find_supersede(notes):
    hits = []
    for n in notes:
        if SUPERSEDE_RE.search(n["text"]):
            lines = [l.strip() for l in n["text"].splitlines() if SUPERSEDE_RE.search(l)]
            hits.append((n["rel"], lines[:3]))
    return hits


def find_stale(notes, days):
    cutoff = datetime.datetime.now().timestamp() - days * 86400
    rows = [(n["rel"], datetime.date.fromtimestamp(n["mtime"]).isoformat())
            for n in notes if n["mtime"] < cutoff]
    return sorted(rows, key=lambda x: x[1])


def build_report(vault, notes, dups, sup, stale, days):
    today = datetime.date.today().isoformat()
    r = ["---", f"title: Brain consolidation report {today}", "source: cowork",
         "tags: [cowork, session, brain, consolidation]", "---", "",
         f"# Brain consolidation report — {today}", "",
         f"Scanned **{len(notes)}** notes in `{vault}`. Report-only; nothing was changed.", "",
         "## Near-duplicate candidates (review → merge or differentiate)"]
    r += [f"- {s:.0%} overlap — `{a}` ⟷ `{b}`" for s, a, b in dups[:30]] or ["- none above threshold"]
    r += ["", "## Supersede / outdated markers found in text"]
    if sup:
        for rel, lines in sup:
            r.append(f"- `{rel}`")
            r += [f"    - {l[:160]}" for l in lines]
    else:
        r.append("- none")
    r += ["", f"## Stale notes (not modified in {days}+ days)"]
    r += [f"- {d} — `{rel}`" for rel, d in stale] or ["- none"]
    r += ["", "## Suggested actions",
          "- Near-dup pairs: merge the weaker into the stronger and add a [[link]], or clarify scope.",
          "- Supersede markers: confirm the old note links to its replacement (add `superseded-by:` frontmatter).",
          "- Stale notes: re-confirm still true, or archive."]
    return today, "\n".join(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--threshold", type=float, default=0.5)
    a = ap.parse_args()
    notes = read_notes(a.vault)
    dups = find_near_dups(notes, a.threshold)
    sup = find_supersede(notes)
    stale = find_stale(notes, a.days)
    today, report = build_report(a.vault, notes, dups, sup, stale, a.days)
    out_path = os.path.join(a.vault, "Sessions", f"brain-consolidation-{today}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    Path(out_path).write_text(report, encoding="utf-8")
    print(f"wrote Sessions/brain-consolidation-{today}.md | "
          f"notes={len(notes)} near_dups={len(dups)} supersede={len(sup)} stale={len(stale)}")


if __name__ == "__main__":
    main()
