"""Check/install canonical Brain skill files in the two known Codex installations."""
import argparse
import datetime
import hashlib
import shutil
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "cowork-skill"
TARGETS = [Path.home() / ".codex/skills/obsidian-brain"]


def sync(source, targets, apply=False):
    different = []
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    files = [source / "SKILL.md", *sorted((source / "references").glob("*.md"))]
    for target in targets:
        for src in files:
            dest = target / src.relative_to(source)
            content = src.read_bytes()
            if dest.exists() and hashlib.sha256(content).digest() == hashlib.sha256(dest.read_bytes()).digest():
                continue
            different.append(str(dest))
            if apply:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.copy2(dest, dest.with_name(dest.name + ".bak-" + stamp))
                dest.write_bytes(content)
    return different


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Install canonical files, retaining backups")
    parser.add_argument("--target", type=Path, action="append", help="Explicit skill installation directory; repeat for multiple clients")
    args = parser.parse_args()
    paths = sync(SOURCE, args.target or TARGETS, args.apply)
    for path in paths:
        print(("Updated " if args.apply else "Drift: ") + path)
    if not paths:
        print("Selected installed skills match the canonical source.")
    raise SystemExit(0 if args.apply or not paths else 1)
