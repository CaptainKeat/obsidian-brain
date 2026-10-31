"""Dry-run by default. Add explicit project hubs and repair exact known links.

Backups and the JSON receipt must live outside the vault. Rollback restores only
files still matching this migration's output, refusing later user/agent edits.
"""
import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain_memory as bm
from brain_graph_links import Catalog, HUB_DIR, hub_path, hub_text, navigation, project_key


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_receipt(path, report):
    # Windows readers/antivirus may briefly hold a destination without delete
    # sharing. Retry only the journal replacement, never the note mutation.
    for attempt in range(8):
        try:
            bm._atomic_write(path, json.dumps(report, indent=2))
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))


def plan(vault):
    vault = Path(vault).resolve()
    catalog = Catalog(vault)
    entries = []
    projects = {}
    snapshots = {}
    assignments = {}
    for rel in catalog.paths.values():
        raw = (vault / rel).read_bytes()
        text = raw.decode("utf-8-sig")
        snapshots[rel] = (raw, text)
        metadata, _ = bm.parse_frontmatter(text)
        if metadata.get("type") == "project-hub":
            continue
        project = metadata.get("project")
        # Existing project overview notes provide an explicit identity too.
        title = str(metadata.get("title", ""))
        if not project and title.startswith("Projects/"):
            project = title[len("Projects/"):]
        if not project and rel.startswith("Projects/") and rel.count("/") == 1:
            project = Path(rel).stem
        if isinstance(project, str) and project_key(project):
            assignments[rel] = project
            projects.setdefault(project_key(project), project)
    for key, project in sorted(projects.items()):
        if catalog.hub(project):
            continue
        rel = hub_path(project)
        if rel.casefold() in catalog.paths:
            raise RuntimeError("Hub identity collision: " + rel)
        entries.append({"path": rel, "before": None, "after": hub_text(project), "kind": "hub"})
        catalog.paths[rel.casefold()] = rel
        catalog.hubs[key] = [rel]
    unresolved = Counter()
    repairs = []
    assignments_count = 0
    for rel, (raw, text) in snapshots.items():
        metadata, _ = bm.parse_frontmatter(text)
        if metadata.get("type") == "project-hub":
            continue
        new, fixed, missing = navigation(text, catalog, project=assignments.get(rel),
            sources=metadata.get("sources", []) if isinstance(metadata.get("sources", []), list) else [],
            supersedes=metadata.get("supersedes", []) if isinstance(metadata.get("supersedes", []), list) else [],
            self_path=rel)
        unresolved.update(missing)
        repairs.extend({"note": rel, **r} for r in fixed)
        if new != text:
            entries.append({"path": rel, "before": sha(raw), "after": new, "kind": "note"})
            if rel in assignments:
                assignments_count += 1
    map_rel = "Brain Project Map.md"
    map_path = vault / map_rel
    # Only own a clearly marked generated map. Never overwrite a user note.
    map_header = "<!-- brain-project-map:v1 -->"
    if map_path.exists() and not map_path.read_text(encoding="utf-8-sig").startswith(map_header):
        raise RuntimeError("Existing user map preserved; choose another migration map name")
    text = map_header + "\n# Brain project map\n\n"
    text += "Hubs group explicit project assignments. Related workstreams retain their original labels.\n\n"
    for key, paths in sorted(catalog.hubs.items()):
        if len(paths) == 1:
            text += "- [[" + paths[0][:-3] + "|" + key.replace("|", " ") + "]]\n"
    old = map_path.read_bytes() if map_path.exists() else None
    if old != text.encode("utf-8"):
        entries.append({"path": map_rel, "before": sha(old) if old is not None else None,
                        "after": text, "kind": "map"})
    return {"vault": str(vault), "entries": entries, "repairs": repairs,
            "unresolved": dict(unresolved), "project_assignments": len(assignments),
            "changed_assignments": assignments_count, "project_labels": len(projects)}


def apply_plan(data, backup_dir):
    vault = Path(data["vault"]).resolve()
    backup = Path(backup_dir).resolve()
    if backup == vault or backup.is_relative_to(vault):
        raise ValueError("Backups must be outside the vault")
    backup.mkdir(parents=True, exist_ok=True)
    receipt = backup / "receipt.json"
    if receipt.exists():
        raise ValueError("Use a fresh backup directory; receipt already exists")
    rows = []
    # Save the complete plan and all original bytes before any vault mutation.
    for i, entry in enumerate(data["entries"]):
        target = bm.resolve_note_path(entry["path"], roots={"vault": vault}, must_exist=False)
        raw = target.read_bytes() if target.exists() else None
        if (sha(raw) if raw is not None else None) != entry["before"]:
            raise RuntimeError("Changed since planning; rerun dry-run: " + entry["path"])
        original = None
        if raw is not None:
            original = f"original-{i:05d}.bin"
            (backup / original).write_bytes(raw)
        rows.append({k: v for k, v in entry.items() if k != "after"} |
                    {"after_sha256": sha(entry["after"].encode("utf-8")),
                     "backup": original, "status": "pending"})
    report = {k: v for k, v in data.items() if k != "entries"}
    report["entries"] = rows
    save_receipt(receipt, report)
    for entry, row in zip(data["entries"], rows):
        target = bm.resolve_note_path(entry["path"], roots={"vault": vault}, must_exist=False)
        with bm._note_lock(target):
            raw = target.read_bytes() if target.exists() else None
            if (sha(raw) if raw is not None else None) != entry["before"]:
                row["status"] = "conflict"
            else:
                bm._atomic_write(target, entry["after"])
                row["status"] = "applied"
        save_receipt(receipt, report)
    return report


def rollback(receipt_path):
    receipt = Path(receipt_path).resolve()
    report = json.loads(receipt.read_text())
    vault = Path(report["vault"]).resolve()
    for row in reversed(report["entries"]):
        if row["status"] not in {"applied", "rollback-conflict", "pending"}:
            continue
        target = bm.resolve_note_path(row["path"], roots={"vault": vault}, must_exist=False)
        with bm._note_lock(target):
            current = target.read_bytes() if target.exists() else None
            current_hash = sha(current) if current is not None else None
            if current_hash == row["before"]:
                row["status"] = "rolled-back"
            elif current_hash != row["after_sha256"]:
                row["status"] = "rollback-conflict"
            elif row["backup"]:
                original = (receipt.parent / row["backup"]).read_bytes()
                if sha(original) != row["before"]:
                    raise RuntimeError("Backup hash mismatch")
                # Preserve the original encoding/newlines exactly.
                import os, tempfile
                fd, temp = tempfile.mkstemp(dir=target.parent)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(original); handle.flush(); os.fsync(handle.fileno())
                os.replace(temp, target)
                row["status"] = "rolled-back"
            else:
                target.unlink()  # Exact migration-created file only; hash checked.
                row["status"] = "rolled-back"
        save_receipt(receipt, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.rollback:
        result = rollback(args.rollback)
    else:
        if not args.vault:
            parser.error("--vault is required")
        result = plan(args.vault)
        if args.apply:
            if not args.backup_dir:
                parser.error("--backup-dir is required with --apply")
            result = apply_plan(result, args.backup_dir)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"entries": len(result["entries"]),
                      "kinds": dict(Counter(e["kind"] for e in result["entries"])),
                      "statuses": dict(Counter(e.get("status", "planned") for e in result["entries"])),
                      "repairs": len(result["repairs"]),
                      "unresolved_targets": len(result["unresolved"]),
                      "project_assignments": result["project_assignments"]}, indent=2))
    if any(e.get("status") in {"conflict", "rollback-conflict"} for e in result["entries"]):
        raise SystemExit(2)
