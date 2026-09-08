"""
rag_indexer.py - Passive RAG indexer for the Obsidian "brain" (v2.1).

Indexes Markdown across MULTIPLE roots into one local LanceDB vector store and
exposes /search for any client (Claude via the obsidian-brain MCP, and the
VTuber memory proxy). Runs locally on CPU.

v2 upgrades (all backward-compatible; old `GET /search?q=&k=` still works):
  - #2 folder/namespace filters   -> ?include=Patterns,Gotchas  ?exclude=VTuber-Memory  ?roots=vault,projects
  - #3 optional cross-encoder rerank (RAG_RERANK=1)             -> ?rerank=1
  - #3 swappable embedding model (EMBED_MODEL=...) with automatic
        rebuild when the vector dimension changes
  - #4 hybrid BM25 + vector retrieval, fused with Reciprocal Rank Fusion (always on)
  - #6 graph expansion over [[wikilinks]]                        -> ?expand=1

v2.1 hardening (churn protection; fixes the runaway-CPU loop where an external
process rewrites the same files forever and the indexer re-embeds every event):
  - Content-hash short-circuit: index_file() skips the expensive re-embed when
    the file's sha256 is identical to the last-indexed content for that doc_id.
  - Per-file circuit breaker: if a file is reindexed more than RAG_CHURN_MAX
    times within RAG_CHURN_WINDOW seconds, it is throttled to at most one
    reindex per RAG_CHURN_COOLDOWN seconds (one loud warning is logged) until
    it receives no events for RAG_CHURN_SETTLE seconds, then behavior resumes.
  - Delete debounce: deletes are held for RAG_DELETE_DEBOUNCE seconds and
    cancelled if the same path is created/modified again (the classic editor
    atomic-save pattern: write temp -> delete original -> rename temp), so an
    atomic save no longer causes a spurious purge+reindex cycle.

Pure-python search helpers live in brain_search.py (import-safe, unit-tested).

Roots:
  - vault    : the whole Obsidian Knowledge-Base (all .md). LIVE-watched.
  - projects : examples/projects project docs, shallow only (depth<=2). Refreshed on
               startup + POST /reindex (not live-watched).

Env:
  VAULT_PATH, PROJECTS_PATH, PROJECTS_MAX_DEPTH, DB_PATH, RAG_PORT
  EMBED_MODEL          default all-MiniLM-L6-v2  (e.g. BAAI/bge-base-en-v1.5)
  RAG_RERANK           "1" to enable cross-encoder rerank (default off)
  RERANK_MODEL         default BAAI/bge-reranker-base
  RAG_EXPAND           "1" to expand via [[links]] by default (default off)
  RAG_DEFAULT_EXCLUDE  comma list of folders always excluded (e.g. VTuber-Memory)
  RAG_CHURN_MAX        reindexes within window before throttling (default 10)
  RAG_CHURN_WINDOW     rolling window in seconds (default 300)
  RAG_CHURN_COOLDOWN   min seconds between reindexes while throttled (default 60)
  RAG_CHURN_SETTLE     quiet seconds before a throttled file recovers (default 120)
  RAG_DELETE_DEBOUNCE  seconds a delete is held before purging (default 2.0)
"""
import os
import time
import hashlib
import threading
from collections import deque
from pathlib import Path

from datetime import timedelta

import lancedb
import pyarrow as pa
from sentence_transformers import SentenceTransformer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from fastapi import FastAPI
import uvicorn

import brain_search as bs

VAULT = os.environ.get("VAULT_PATH", str(Path(__file__).resolve().parent / "examples" / "vault"))
PROJECTS = os.environ.get("PROJECTS_PATH", str(Path(__file__).resolve().parent / "examples" / "projects"))
PROJECTS_MAX_DEPTH = int(os.environ.get("PROJECTS_MAX_DEPTH", "2"))
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "lancedb"))
PORT = int(os.environ.get("RAG_PORT", "5180"))
EMBED_MODEL = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
RERANK = os.environ.get("RAG_RERANK", "0") == "1"
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-base")
EXPAND_DEFAULT = os.environ.get("RAG_EXPAND", "0") == "1"
DEFAULT_EXCLUDE = bs.parse_csv_param(os.environ.get("RAG_DEFAULT_EXCLUDE", ""))
TABLE = "vault"

# --- churn-protection tunables ----------------------------------------------
INDEX_DEBOUNCE_SECS = 1.5   # existing pending-index debounce (unchanged)
DELETE_DEBOUNCE_SECS = float(os.environ.get("RAG_DELETE_DEBOUNCE", "2.0"))
CHURN_MAX = int(os.environ.get("RAG_CHURN_MAX", "10"))
CHURN_WINDOW = float(os.environ.get("RAG_CHURN_WINDOW", "300"))
CHURN_COOLDOWN = float(os.environ.get("RAG_CHURN_COOLDOWN", "60"))
CHURN_SETTLE = float(os.environ.get("RAG_CHURN_SETTLE", "120"))

EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", ".git", "dist", "build", ".next",
    "site-packages", "__pycache__", ".cache", "huggingface", "models",
    "weights", "vendor", "target", "out", ".pytest_cache", ".mypy_cache",
    ".obsidian", ".trash", ".idea", ".vscode", ".egg-info",
}

# label -> config. watch=True means live filesystem watcher.
ROOTS = [
    {"label": "vault", "path": VAULT, "max_depth": None, "watch": True},
    {"label": "projects", "path": PROJECTS, "max_depth": PROJECTS_MAX_DEPTH, "watch": False},
]

# Cap torch CPU threads (v2.2): with the default (all 16 logical cores) every
# rerank/embed on tiny batches burned ~17 CPU-s per /search, mostly OpenMP
# spin-wait — the second half of the 2026-07 sustained-CPU incident. A small
# thread cap gives near-identical wall time on these workloads at a fraction
# of the CPU-seconds.
try:
    import torch
    torch.set_num_threads(int(os.environ.get("RAG_TORCH_THREADS", "4")))
except Exception as _e:
    print(f"[rag] torch thread cap skipped ({_e})", flush=True)

print(f"[rag] loading embed model {EMBED_MODEL} (CPU)...", flush=True)
try:
    model = SentenceTransformer(EMBED_MODEL, device="cpu")
except Exception as e:
    print(f"[rag] embed model '{EMBED_MODEL}' failed ({e}); falling back to all-MiniLM-L6-v2", flush=True)
    EMBED_MODEL = "all-MiniLM-L6-v2"
    model = SentenceTransformer(EMBED_MODEL, device="cpu")
EMBED_DIM = int(model.get_sentence_embedding_dimension())
print(f"[rag] embed dim = {EMBED_DIM}", flush=True)
db = lancedb.connect(DB_PATH)
_lock = threading.Lock()

# --- in-memory lexical corpus + link graph (kept in sync with the table) ----
LEX_DOCS = {}     # doc_id -> [ {root, path, chunk}, ... ]
SLUG2META = {}    # note slug -> {path, root, first}  (for [[link]] expansion)
LINKS = {}        # note slug -> set(linked slugs)
_lex = {"bm25": None, "flat": [], "dirty": True}
_reranker = {"obj": None, "tried": False}
_last_hash = {}   # doc_id -> sha256 hex of the last-indexed text (in-memory)

# --- table maintenance (v2.2, 2026-07-13) -----------------------------------
# Every delete/add/update writes a new LanceDB dataset version (and usually a
# tiny new fragment). Nothing ever compacted them, so months of file churn left
# ~5000 manifests + 1800 fragments for <1000 rows, and every /search + /health
# had to plan across all of them (~11 s CPU per request, leaking tokio blocking
# threads -> the sustained ~30% CPU incident). optimize() compacts fragments
# and prunes old versions; run it shortly after startup, then whenever enough
# mutations accumulate or on a slow timer.
MAINT_EVERY_MUTATIONS = int(os.environ.get("RAG_MAINT_MUTATIONS", "200"))
MAINT_INTERVAL_SECS = float(os.environ.get("RAG_MAINT_INTERVAL", "3600"))
_maint = {"mutations": 0, "last": 0.0}


def _bump_mutations(n=1):
    _maint["mutations"] += n


def optimize_table(reason=""):
    try:
        with _lock:
            _get_table().optimize(cleanup_older_than=timedelta(minutes=10))
        _maint["mutations"] = 0
        _maint["last"] = time.time()
        print(f"[rag] table optimized (compact + version cleanup) {reason}", flush=True)
    except Exception as e:
        print(f"[rag] table optimize failed ({e})", flush=True)


def _maint_loop():
    time.sleep(20.0)
    optimize_table("(startup)")
    while True:
        time.sleep(30.0)
        if _maint["mutations"] >= MAINT_EVERY_MUTATIONS or (
                _maint["mutations"] > 0
                and time.time() - _maint["last"] > MAINT_INTERVAL_SECS):
            optimize_table(f"(mutations={_maint['mutations']})")


def _schema():
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("root", pa.string()),
        pa.field("path", pa.string()),
        pa.field("mtime", pa.float64()),
        pa.field("chunk", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
    ])


def _get_table():
    try:
        if TABLE in db.table_names():
            return db.open_table(TABLE)
        return db.create_table(TABLE, schema=_schema())
    except Exception:
        return db.open_table(TABLE)


def _root_for(abspath):
    ap = os.path.abspath(abspath)
    for r in ROOTS:
        base = os.path.abspath(r["path"])
        if ap.lower().startswith(base.lower() + os.sep):
            return r
    return None


def _doc_id(abspath, root):
    rel = os.path.relpath(abspath, root["path"]).replace(os.sep, "/")
    return f"{root['label']}/{rel}", rel


def _sql_quote(s):
    return s.replace("'", "''")


def _text_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def walk_files(root):
    base = root["path"]
    maxd = root["max_depth"]
    if not os.path.isdir(base):
        return
    base_depth = len(Path(base).parts)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d.lower() not in EXCLUDE_DIRS]
        depth = len(Path(dirpath).parts) - base_depth
        if maxd is not None and depth >= maxd:
            dirnames[:] = []
        for fn in filenames:
            # Changelogs are high-churn dependency history, not useful project memory.
            # Some exceed a megabyte and can monopolize CPU for many minutes.
            if fn.lower() == "changelog.md":
                continue
            if fn.lower().endswith(".md"):
                fp = os.path.join(dirpath, fn)
                rel_parts = len(Path(os.path.relpath(fp, base)).parts)
                if maxd is None or rel_parts <= maxd:
                    yield fp


def chunk_text(text, size=600, overlap=80):
    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 20]
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 2 <= size:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                yield buf
            if len(p) > size:
                for i in range(0, len(p), size - overlap):
                    yield p[i:i + size]
                buf = ""
            else:
                buf = p
    if buf:
        yield buf


# --- lexical / graph bookkeeping -------------------------------------------

def register_lex(doc_id, root_label, rel, text, chunks=None):
    """Mirror a doc into the in-memory lexical corpus + link graph."""
    if chunks is None:
        chunks = list(chunk_text(text))
    LEX_DOCS[doc_id] = [{"root": root_label, "path": rel, "chunk": c} for c in chunks]
    slug = bs.path_to_slug(rel)
    LINKS[slug] = bs.parse_wikilinks(text)
    SLUG2META[slug] = {"path": rel, "root": root_label, "first": (chunks[0] if chunks else "")}
    _lex["dirty"] = True


def unregister_lex(doc_id, rel):
    LEX_DOCS.pop(doc_id, None)
    slug = bs.path_to_slug(rel)
    LINKS.pop(slug, None)
    SLUG2META.pop(slug, None)
    _lex["dirty"] = True


def _ensure_lex():
    if not _lex["dirty"]:
        return
    flat = []
    for rows in LEX_DOCS.values():
        flat.extend(rows)
    bm = bs.BM25().build([bs.tokenize(x["chunk"]) for x in flat]) if flat else None
    _lex["flat"] = flat
    _lex["bm25"] = bm
    _lex["dirty"] = False


def _get_reranker():
    if _reranker["obj"] is not None or _reranker["tried"]:
        return _reranker["obj"]
    _reranker["tried"] = True
    try:
        from sentence_transformers import CrossEncoder
        print(f"[rag] loading reranker {RERANK_MODEL} ...", flush=True)
        _reranker["obj"] = CrossEncoder(RERANK_MODEL, device="cpu")
    except Exception as e:
        print(f"[rag] reranker unavailable ({e}); continuing without rerank", flush=True)
        _reranker["obj"] = None
    return _reranker["obj"]


# --- indexing --------------------------------------------------------------

def index_file(abspath, root=None, mtime=None, text=None):
    """Index (or re-index) one file.

    Returns the number of chunks embedded, or None when the content hash was
    unchanged and the expensive re-embed was skipped entirely.
    """
    root = root or _root_for(abspath)
    if not root:
        return 0
    doc_id, rel = _doc_id(abspath, root)
    if mtime is None:
        try:
            mtime = os.path.getmtime(abspath)
        except OSError:
            return 0
    if text is None:
        try:
            text = Path(abspath).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"[rag] read fail {abspath}: {e}", flush=True)
            return 0

    # Content-hash short-circuit: if the text is byte-identical to what we
    # last embedded for this doc, skip the expensive encode+rewrite entirely.
    # (Covers atomic saves / touch-only rewrites that only bump mtime.)
    h = _text_hash(text)
    if _last_hash.get(doc_id) == h:
        if doc_id not in LEX_DOCS:  # keep lexicon warm if it somehow got dropped
            register_lex(doc_id, root["label"], rel, text)
        # best-effort mtime bookkeeping so a restart's full_scan won't re-embed
        with _lock:
            try:
                _get_table().update(where=f"id = '{_sql_quote(doc_id)}'",
                                    values={"mtime": float(mtime)})
            except Exception:
                pass
        _bump_mutations()
        return None

    chunks = list(chunk_text(text))
    rows = []
    if chunks:
        batch_size = int(os.environ.get("RAG_EMBED_BATCH", "16"))
        vectors = model.encode(
            chunks,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=False,
        )
        for ch, vector in zip(chunks, vectors):
            rows.append({"id": doc_id, "root": root["label"], "path": rel,
                         "mtime": float(mtime), "chunk": ch,
                         "vector": vector.astype("float32").tolist()})
    with _lock:
        tbl = _get_table()
        try:
            tbl.delete(f"id = '{_sql_quote(doc_id)}'")
        except Exception:
            pass
        if rows:
            tbl.add(rows)
    _bump_mutations(2)
    register_lex(doc_id, root["label"], rel, text, chunks=chunks)
    _last_hash[doc_id] = h
    return len(rows)


def delete_file(abspath, root=None):
    root = root or _root_for(abspath)
    if not root:
        return
    doc_id, rel = _doc_id(abspath, root)
    with _lock:
        try:
            _get_table().delete(f"id = '{_sql_quote(doc_id)}'")
            print(f"[rag] purged {doc_id}", flush=True)
        except Exception:
            pass
    unregister_lex(doc_id, rel)
    _last_hash.pop(doc_id, None)
    _bump_mutations()


def full_scan():
    tbl = _get_table()
    try:
        known_rows = tbl.search().limit(5_000_000).select(["id", "mtime"]).to_list()
    except Exception:
        known_rows = []
    known = {r["id"]: r.get("mtime", 0.0) for r in known_rows}

    current_ids = set()
    per_root = {}
    embedded = skipped = 0
    for root in ROOTS:
        n = 0
        for f in walk_files(root):
            n += 1
            doc_id, rel = _doc_id(f, root)
            current_ids.add(doc_id)
            try:
                mt = os.path.getmtime(f)
            except OSError:
                continue
            # read once; used for embedding (if changed) AND lexical/graph (always)
            try:
                text = Path(f).read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = ""
            if doc_id in known and abs(known[doc_id] - mt) < 1e-6:
                skipped += 1
                register_lex(doc_id, root["label"], rel, text)  # keep lexicon warm
                _last_hash[doc_id] = _text_hash(text)           # seed hash cache
                continue
            if index_file(f, root, mtime=mt, text=text) is None:
                skipped += 1  # hash matched: mtime drifted but content identical
            else:
                embedded += 1
        per_root[root["label"]] = n

    stale = set(known) - current_ids
    with _lock:
        t = _get_table()
        for sid in stale:
            t.delete(f"id = '{_sql_quote(sid)}'")
    for sid in stale:
        _last_hash.pop(sid, None)
    _lex["dirty"] = True
    print(f"[rag] scan: {per_root} | embedded {embedded}, skipped {skipped}, "
          f"purged {len(stale)} | lex_docs {len(LEX_DOCS)}", flush=True)
    return per_root, embedded, skipped, len(stale)


class VaultHandler(FileSystemEventHandler):
    """Watchdog handler with churn protection.

    - _pending:   normcase(path) -> (original_path, event_time). Indexed after
                  INDEX_DEBOUNCE_SECS of quiet (as before).
    - _deleted:   normcase(path) -> (original_path, delete_time). Purged only
                  after DELETE_DEBOUNCE_SECS, and cancelled if the same path is
                  created/modified again (editor atomic-save pattern) or if the
                  file exists again when the debounce expires.
    - _history:   normcase(path) -> deque of recent reindex timestamps (rolling
                  CHURN_WINDOW). Reaching CHURN_MAX within the window trips the
                  circuit breaker.
    - _throttled: normcase(path) -> {"path", "last_index", "last_event"}.
                  While throttled, the file is reindexed at most once per
                  CHURN_COOLDOWN seconds; after CHURN_SETTLE seconds with no
                  events, it recovers to normal behavior.

    Dict mutations here happen from the watchdog thread and the drain thread;
    individual dict operations are atomic under the GIL (same assumption the
    original code made), and iteration uses list() snapshots.
    """

    def __init__(self):
        self._pending = {}
        self._deleted = {}
        self._history = {}
        self._throttled = {}

    def _touch(self, path):
        if not path or not path.lower().endswith(".md"):
            return
        r = _root_for(path)
        if r and not any(p.lower() in EXCLUDE_DIRS for p in Path(path).parts):
            key = os.path.normcase(path)
            now = time.time()
            # a create/modify for a path with a pending delete = atomic save;
            # cancel the purge and just (re)index instead.
            self._deleted.pop(key, None)
            self._pending[key] = (path, now)
            st = self._throttled.get(key)
            if st:
                st["last_event"] = now

    def on_modified(self, e):
        if not e.is_directory:
            self._touch(e.src_path)

    def on_created(self, e):
        if not e.is_directory:
            self._touch(e.src_path)

    def on_deleted(self, e):
        if not e.is_directory and e.src_path.lower().endswith(".md"):
            key = os.path.normcase(e.src_path)
            self._deleted[key] = (e.src_path, time.time())
            # don't try to index a file that just got deleted
            self._pending.pop(key, None)
            st = self._throttled.get(key)
            if st:
                st["last_event"] = time.time()

    def on_moved(self, e):
        if not e.is_directory:
            if e.src_path.lower().endswith(".md"):
                key = os.path.normcase(e.src_path)
                self._deleted[key] = (e.src_path, time.time())
                self._pending.pop(key, None)
            self._touch(getattr(e, "dest_path", ""))

    def drain_loop(self):
        while True:
            time.sleep(1.0)
            now = time.time()

            # ---- debounced deletes (atomic-save safe) ----------------------
            for key, (path, t) in list(self._deleted.items()):
                if now - t < DELETE_DEBOUNCE_SECS:
                    continue
                self._deleted.pop(key, None)
                if key in self._pending:
                    continue  # recreated already; pending reindex handles it
                try:
                    if os.path.exists(path):
                        # file reappeared (rename landed) but we saw no create
                        # event for it; reindex instead of purging.
                        self._pending.setdefault(key, (path, now))
                        continue
                    delete_file(path)
                except Exception as ex:
                    print(f"[rag] delete fail {path}: {ex}", flush=True)

            # ---- throttle recovery -----------------------------------------
            for key in list(self._throttled):
                st = self._throttled.get(key)
                if st and key not in self._pending and key not in self._deleted \
                        and now - st["last_event"] > CHURN_SETTLE:
                    self._throttled.pop(key, None)
                    self._history.pop(key, None)
                    print(f"[rag] churn settled for {st['path']} "
                          f"(quiet {int(CHURN_SETTLE)}s); resuming normal reindexing",
                          flush=True)

            # ---- debounced (re)indexing with per-file circuit breaker ------
            for key, (path, t) in list(self._pending.items()):
                if now - t <= INDEX_DEBOUNCE_SECS:
                    continue
                st = self._throttled.get(key)
                if st and now - st["last_index"] < CHURN_COOLDOWN:
                    # throttled and still cooling down: postpone so this entry
                    # becomes due once the cooldown elapses (new events push it
                    # later, which is fine -- the file is still churning).
                    self._pending[key] = (path, st["last_index"] + CHURN_COOLDOWN
                                          - INDEX_DEBOUNCE_SECS)
                    continue
                self._pending.pop(key, None)

                hist = self._history.setdefault(key, deque())
                hist.append(now)
                while hist and now - hist[0] > CHURN_WINDOW:
                    hist.popleft()
                if st is None and len(hist) >= CHURN_MAX:
                    st = self._throttled[key] = {"path": path, "last_index": now,
                                                 "last_event": now}
                    print(f"[rag] WARNING: {path} re-triggered {len(hist)} times in "
                          f"{int(CHURN_WINDOW)}s — throttling, will only reindex at "
                          f"most once per {int(CHURN_COOLDOWN)}s until it settles",
                          flush=True)
                elif st:
                    st["last_index"] = now

                try:
                    n = index_file(path)
                    if n is None:
                        print(f"[rag] unchanged {path} (content hash match; "
                              f"skipped re-embed)", flush=True)
                    else:
                        print(f"[rag] reindexed {path} ({n} chunks)", flush=True)
                except Exception as ex:
                    print(f"[rag] reindex fail {path}: {ex}", flush=True)


# --- search ----------------------------------------------------------------

def _key(path, chunk):
    return path + "\x00" + chunk


def do_search(q, k=5, include=None, exclude=None, roots=None,
              rerank=None, expand=None, candidates=None):
    include = bs.parse_csv_param(include)
    exclude = bs.parse_csv_param(exclude) + list(DEFAULT_EXCLUDE)
    roots = set(bs.parse_csv_param(roots))
    use_rerank = RERANK if rerank is None else (bool(int(rerank)) if str(rerank).isdigit() else bool(rerank))
    use_expand = EXPAND_DEFAULT if expand is None else (bool(int(expand)) if str(expand).isdigit() else bool(expand))
    cand = int(candidates) if candidates else max(40, k * 8)

    pool = {}
    vorder = []
    emb = model.encode(q, normalize_embeddings=True).astype("float32").tolist()
    with _lock:
        try:
            vrows = _get_table().search(emb).limit(cand).to_list()
        except Exception:
            vrows = []
    for r in vrows:
        path, chunk = r.get("path", ""), r.get("chunk", "")
        if roots and r.get("root") not in roots:
            continue
        if not bs.folder_match(path, include, exclude):
            continue
        key = _key(path, chunk)
        pool.setdefault(key, {"root": r.get("root"), "path": path, "chunk": chunk})
        vorder.append(key)

    _ensure_lex()
    lorder = []
    if _lex["bm25"]:
        for idx, _sc in _lex["bm25"].top_n(q, cand):
            item = _lex["flat"][idx]
            path, chunk = item["path"], item["chunk"]
            if roots and item["root"] not in roots:
                continue
            if not bs.folder_match(path, include, exclude):
                continue
            key = _key(path, chunk)
            pool.setdefault(key, {"root": item["root"], "path": path, "chunk": chunk})
            lorder.append(key)

    fused = bs.reciprocal_rank_fusion([vorder, lorder])
    ranked = sorted(fused, key=lambda kk: fused[kk], reverse=True)

    window = ranked[: max(k * 4, 20)]
    if use_rerank and window:
        rr = _get_reranker()
        if rr is not None:
            try:
                pairs = [(q, pool[key]["chunk"]) for key in window]
                scores = rr.predict(pairs)
                window = [key for key, _ in sorted(zip(window, scores),
                                                   key=lambda x: float(x[1]), reverse=True)]
                wset = set(window)
                ranked = window + [k_ for k_ in ranked if k_ not in wset]
            except Exception as ex:
                print(f"[rag] rerank failed ({ex}); using fused order", flush=True)

    chosen = ranked[:k]
    results = []
    seen_paths = set()
    for key in chosen:
        p = pool[key]
        seen_paths.add(p["path"])
        results.append({
            "source": p["path"], "root": p["root"], "path": p["path"],
            "snippet": p["chunk"][:300], "score": round(float(fused.get(key, 0.0)), 5),
            "via": "vector+lexical",
        })

    if use_expand:
        added = 0
        for key in chosen:
            slug = bs.path_to_slug(pool[key]["path"])
            for lk in LINKS.get(slug, ()):
                meta = SLUG2META.get(lk)
                if not meta or meta["path"] in seen_paths:
                    continue
                if roots and meta["root"] not in roots:
                    continue
                if not bs.folder_match(meta["path"], include, exclude):
                    continue
                results.append({
                    "source": meta["path"], "root": meta["root"], "path": meta["path"],
                    "snippet": (meta["first"] or "")[:300], "score": 0.0, "via": "link",
                })
                seen_paths.add(meta["path"])
                added += 1
                if added >= k:
                    break
            if added >= k:
                break

    return results


# --- HTTP ------------------------------------------------------------------

app = FastAPI(title="Obsidian RAG Indexer (v2)")


@app.on_event("startup")
async def _cap_http_threadpool():
    """Cap the AnyIO worker pool for sync endpoints (v2.3, 2026-07-13).

    FastAPI runs plain `def` endpoints in AnyIO's default thread pool, which
    grows to 40 worker threads and never shrinks; council recall bursts (4+
    queries per deliberation round x 7 backends) grew it toward that cap and
    left an 83-thread baseline. /search is largely serialized under _lock
    anyway, so a handful of workers is plenty.
    """
    try:
        from anyio import to_thread
        limiter = to_thread.current_default_thread_limiter()
        limiter.total_tokens = int(os.environ.get("RAG_HTTP_THREADS", "4"))
        print(f"[rag] http worker threads capped at {limiter.total_tokens}", flush=True)
    except Exception as e:
        print(f"[rag] http threadpool cap skipped ({e})", flush=True)


@app.get("/health")
def health():
    out = {"status": "ok", "model": EMBED_MODEL, "dim": EMBED_DIM,
           "rerank": RERANK, "default_exclude": list(DEFAULT_EXCLUDE),
           "lex_docs": len(LEX_DOCS), "links": len(LINKS), "by_root": {}, "chunks": 0}
    try:
        with _lock:
            out["chunks"] = _get_table().count_rows()
    except Exception:
        pass
    seen = {}
    for rows_ in list(LEX_DOCS.values()):
        for r in rows_:
            seen.setdefault(r["root"], set()).add(r["path"])
    out["by_root"] = {k: len(v) for k, v in seen.items()}
    return out


@app.get("/search")
def search(q: str, k: int = 5, include: str = "", exclude: str = "",
           roots: str = "", rerank: str = "", expand: str = "", candidates: str = ""):
    return do_search(q, k=k, include=include, exclude=exclude, roots=roots,
                     rerank=(rerank or None), expand=(expand or None),
                     candidates=(candidates or None))


@app.post("/reindex")
def reindex():
    per_root, embedded, skipped, purged = full_scan()
    return {"by_root": per_root, "embedded": embedded, "skipped": skipped, "purged": purged}


def _ensure_dim():
    try:
        if TABLE in db.table_names():
            t = db.open_table(TABLE)
            try:
                dim = t.schema.field("vector").type.list_size
            except Exception:
                dim = None
            if dim and dim != EMBED_DIM:
                print(f"[rag] embed dim changed {dim} -> {EMBED_DIM}; rebuilding table", flush=True)
                db.drop_table(TABLE)
    except Exception as e:
        print(f"[rag] dim check skipped ({e})", flush=True)


def main():
    _ensure_dim()
    per_root, embedded, skipped, purged = full_scan()
    print(f"[rag] ready: {per_root}, embedded {embedded}, skipped {skipped}", flush=True)
    handler = VaultHandler()
    obs = Observer()
    for root in ROOTS:
        if root.get("watch") and os.path.isdir(root["path"]):
            obs.schedule(handler, root["path"], recursive=True)
    obs.start()
    threading.Thread(target=handler.drain_loop, daemon=True).start()
    threading.Thread(target=_maint_loop, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
