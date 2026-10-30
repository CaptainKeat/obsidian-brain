"""Read-only live recall checks using the existing local Brain service.

Uses only GET /health and GET /search. No reindex, model load, restart, or vault
writes. Target-note recall is not a measurement of end-to-end answer quality.
"""
import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import statistics
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


def evaluate_hits(hits, case):
    if not isinstance(hits, list):
        raise ValueError("Expected a list of search results")
    identities = [(h["root"], h["path"]) for h in hits]
    target = (case.get("roots", "vault"), case["expected"])
    rank = identities.index(target) + 1 if target in identities else None
    duplicate_count = len(identities) - len(set(identities))
    metadata_snippets = sum(h.get("snippet", "").lstrip().startswith("---") for h in hits)
    weak_snippets = sum(not re.search(r"[^\W_]", h.get("snippet", "")) for h in hits)
    return {
        "rank": rank,
        "passed": rank is not None and duplicate_count == 0 and metadata_snippets == 0 and weak_snippets == 0,
        "duplicates": duplicate_count,
        "metadata_only_snippets": metadata_snippets,
        "weak_snippets": weak_snippets,
        "results": [{k: h.get(k) for k in
                     ("root", "path", "via", "reranked", "warnings", "metadata")}
                    for h in hits],
    }


def load_cases(path):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Cases must be a nonempty JSON list")
    for case in cases:
        if not isinstance(case, dict) or not case.get("query") or not case.get("expected"):
            raise ValueError("Each case needs query and expected")
    return cases


def validate_dest(report, protected):
    resolved = report.resolve()
    if any(resolved == root.resolve() or root.resolve() in resolved.parents
           for root in protected):
        raise ValueError("Report must stay outside indexed vault/project sources")
    if resolved.exists():
        raise ValueError("Report already exists; choose a new filename to preserve evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--cases", type=Path,
                        default=Path(__file__).resolve().parents[1] / "examples/recall-cases.json")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        parser.error("Use the local Brain HTTP origin only")
    import os
    repo = Path(__file__).resolve().parents[1]
    validate_dest(args.report, [Path(os.environ.get("VAULT_PATH", repo / "examples/vault")),
                                Path(os.environ.get("PROJECTS_PATH", repo / "examples/projects"))])
    origin = args.url.rstrip("/")

    def get(endpoint, params=None):
        query = "?" + urlencode(params) if params else ""
        with urlopen(origin + endpoint + query, timeout=30) as response:
            return json.load(response)

    def write_report(report):
        args.report.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects against another run selecting this name.
        with args.report.open("x", encoding="utf-8") as out:
            json.dump(report, out, indent=2)

    try:
        health = get("/health")
        if health.get("status") != "ok":
            raise RuntimeError("Brain service did not report healthy")
    except Exception as exc:
        failed = {"scope": "Read-only recall smoke; no queries executed",
                  "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "summary": {"passed": 0, "cases": 0},
                  "startup_error": f"{type(exc).__name__}: {exc}"}
        write_report(failed)
        print(json.dumps(failed))
        return 1
    rows = []
    for case in load_cases(args.cases):
        start = time.perf_counter()
        params = dict(q=case["query"], roots=case["roots"], include=case["include"],
                      mode=case["mode"], k=5, exclude="VTuber-Memory",
                      rerank="false", expand="false")
        try:
            result = evaluate_hits(get("/search", params), case)
        except Exception as exc:
            result = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        row = dict(case, **result, elapsed_ms=round((time.perf_counter()-start)*1000, 1))
        rows.append(row)
        print(f"{len(rows)}: {'PASS' if row['passed'] else 'FAIL'} "
              f"{case['mode']} rank={row.get('rank')} {case['query']}", flush=True)
    report = {
        "scope": "Known-answer target-note smoke checks; no backend changes; not answer-quality proof",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "health": health,
        "summary": {"passed": sum(r["passed"] for r in rows), "cases": len(rows),
                    "duplicates": sum(r.get("duplicates", 0) for r in rows),
                    "metadata_only_snippets": sum(r.get("metadata_only_snippets", 0) for r in rows),
                    "weak_snippets": sum(r.get("weak_snippets", 0) for r in rows),
                    "warning_results": sum(bool(h.get("warnings")) for r in rows
                                           for h in r.get("results", [])),
                    "median_ms": round(statistics.median(r["elapsed_ms"] for r in rows), 1)},
        "results": rows,
    }
    write_report(report)
    print(json.dumps(report["summary"]))
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
