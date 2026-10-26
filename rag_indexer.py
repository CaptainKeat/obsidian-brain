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
  - projects : configured project docs, shallow only (depth<=2). Refreshed on
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
from fastapi import FastAPI, HTTPException
import uvicorn

import brain_search as bs
import brain_memory as bm
import brain_retrieval as br

VAULT = os.environ.get("VAULT_PATH", str(Path(__file__).parent / "examples" / "vault"))
PROJECTS = os.environ.get("PROJECTS_PATH", str(Path(__file__).parent / "examples" / "projects"))
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
NOTE_META = {}
_lex_lock = threading.RLock()
_index_state = {"last_scan_started": None, "last_scan_completed": None,
                "last_index_error": None, "last_search_error": None}
_watcher_handler = None
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
    if chunks is None:
        chunks = list(chunk_text(text))
    note = br.make_note(root_label, rel, text)
    note["id"] = doc_id
    rows = []
    for chunk in chunks:
        body = br.body_chunk(chunk, note)
        if body:
            rows.append({"root": root_label, "path": rel, "chunk": chunk,
                         "search_text": str(note["metadata"].get("title", "")) + "\n" + body})
    with _lex_lock:
        LEX_DOCS[doc_id] = rows
        NOTE_META[br.identity(root_label, rel)] = note
        _lex["dirty"] = True


def unregister_lex(doc_id, rel):
    with _lex_lock:
        LEX_DOCS.pop(doc_id, None)
        for key in [key for key, note in NOTE_META.items() if note["id"] == doc_id]:
            NOTE_META.pop(key, None)
        _lex["dirty"] = True


def _ensure_lex():
    with _lex_lock:
        if not _lex["dirty"]:
            return
        flat = [row for rows in LEX_DOCS.values() for row in rows]
        bm25 = bs.BM25().build([bs.tokenize(x["search_text"]) for x in flat]) if flat else None
        titles = list(NOTE_META)
        title_bm25 = bs.BM25().build([bs.tokenize(str(NOTE_META[key]["metadata"].get(
            "title", Path(NOTE_META[key]["path"]).stem))) for key in titles]) if titles else None
        by_note = {}
        for i, item in enumerate(flat):
            by_note.setdefault(br.identity(item["root"], item["path"]), []).append(i)
        _lex.update({"flat": flat, "bm25": bm25, "titles": titles,
                     "title_bm25": title_bm25, "by_note": by_note, "dirty": False})


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
            _index_state["last_index_error"] = f"{abspath}: {e}"
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
    _index_state["last_scan_started"] = time.time()
    _index_state["last_index_error"] = None
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
            except Exception as exc:
                _index_state["last_index_error"] = f"{f}: {exc}"
                continue
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
        unregister_lex(sid, "")
    _lex["dirty"] = True
    print(f"[rag] scan: {per_root} | embedded {embedded}, skipped {skipped}, "
          f"purged {len(stale)} | lex_docs {len(LEX_DOCS)}", flush=True)
    if not _index_state["last_index_error"]:
        _index_state["last_scan_completed"] = time.time()
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
                    _index_state["last_index_error"] = f"{path}: {ex}"
                    print(f"[rag] reindex fail {path}: {ex}", flush=True)


# --- search ----------------------------------------------------------------

def do_search(q, k=5, include=None, exclude=None, roots=None,
              rerank=None, expand=None, candidates=None, mode="current"):
    if not q.strip():
        return []
    if not 1 <= k <= 30:
        raise ValueError("k must be between 1 and 30")
    if mode not in {"current", "all"}:
        raise ValueError("mode must be current or all")
    include = bs.parse_csv_param(include)
    exclude = bs.parse_csv_param(exclude) + list(DEFAULT_EXCLUDE)
    roots = set(bs.parse_csv_param(roots))
    if roots - {"vault", "projects"}:
        raise ValueError("roots must contain vault and/or projects")
    use_rerank = RERANK if rerank is None else str(rerank).lower() in {"1", "true"}
    use_expand = EXPAND_DEFAULT if expand is None else str(expand).lower() in {"1", "true"}
    cand = min(1000, max(k, int(candidates) if candidates else max(80, k * 12)))
    with _lex_lock:
        _ensure_lex()
        notes = dict(NOTE_META)
        flat, bm25 = _lex["flat"], _lex["bm25"]
        titles, title_bm25 = _lex["titles"], _lex["title_bm25"]
        by_note = _lex["by_note"]
    superseded = br.superseded_ids(notes)
    allowed = {key: note for key, note in notes.items()
               if (not roots or note["root"] in roots)
               and bs.folder_match(note["path"], include, exclude)
               and (mode == "all" or br.is_current(note, key in superseded))}
    if not allowed:
        return []
    pool, vorder, lorder = {}, [], []
    errors = []

    def add(item, order, method):
        doc = br.identity(item["root"], item["path"])
        if doc not in allowed:
            return
        chunk = item["chunk"]
        evidence = br.body_chunk(chunk, allowed[doc])
        if not evidence:
            return
        key = (doc, chunk)
        p = pool.setdefault(key, {"root": item["root"], "path": item["path"],
                                  "chunk": chunk, "evidence": evidence, "methods": set()})
        p["methods"].add(method)
        if key not in order:
            order.append(key)

    emb = model.encode(q, normalize_embeddings=True).astype("float32").tolist()
    # Filter before top-N; lexical and vector search use the same eligible notes.
    where = "id IN (" + ",".join("'" + _sql_quote(n["id"]) + "'" for n in allowed.values()) + ")"
    with _lock:
        try:
            # Duplicate and metadata-only chunks should not exhaust the note
            # candidate window. Overfetch is bounded and keeps existing vectors.
            vrows = _get_table().search(emb).where(where, prefilter=True).limit(min(1000, cand * 4)).to_list()
        except Exception as exc:
            vrows = []
            errors.append("vector retrieval unavailable; using lexical results")
            _index_state["last_search_error"] = str(exc)
    for item in vrows:
        add(item, vorder, "vector")
    chunk_scores = bm25.score(q) if bm25 else []
    if bm25:
        scored = [(idx, score) for idx, score in enumerate(chunk_scores)
                  if score > 0 and br.identity(flat[idx]["root"], flat[idx]["path"]) in allowed]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        for idx, _score in scored[:cand]:
            add(flat[idx], lorder, "lexical")
    fused = bs.reciprocal_rank_fusion([vorder, lorder])
    # Fuse at note level: vector and lexical may support different passages of
    # the same note. Chunk-only fusion incorrectly treats those as unrelated.
    doc_vorder = list(dict.fromkeys(key[0] for key in vorder))
    # BM25 already scored the full eligible corpus. Preserve its note-level
    # support even outside the materialized chunk window: otherwise a strong
    # vector/title hit loses a whole channel at an arbitrary candidate cutoff.
    doc_lorder = list(dict.fromkeys(br.identity(flat[idx]["root"], flat[idx]["path"])
                                   for idx, _score in scored)) if bm25 else []
    doc_fused = bs.reciprocal_rank_fusion([doc_vorder, doc_lorder])
    # A note's title is a useful identity signal, separate from repeated paths
    # inside incident receipts. Keep this weaker than either primary channel.
    title_order = []
    if title_bm25:
        scores = title_bm25.score(q)
        title_order = [titles[i] for i in sorted(range(len(titles)), key=lambda i: scores[i], reverse=True)
                       if scores[i] > 0 and titles[i] in allowed][:cand]
        for doc, score in bs.reciprocal_rank_fusion([title_order]).items():
            doc_fused[doc] = doc_fused.get(doc, 0.0) + 0.5 * score
            candidates_for_doc = by_note.get(doc, [])
            if candidates_for_doc:
                idx = max(candidates_for_doc, key=lambda i: chunk_scores[i])
                add(flat[idx], [], "title")
    ranked = sorted(pool, key=lambda key: (doc_fused[key[0]], fused.get(key, 0.0)), reverse=True)
    reranked = False
    if use_rerank and ranked:
        rr = _get_reranker()
        if rr is not None:
            try:
                # Rerank one best chunk per note so duplicates cannot crowd the window.
                window = br.select_notes(ranked, pool, max(k * 4, 20))
                scores = rr.predict([(q, pool[key]["evidence"]) for key in window])
                window = [key for key, _ in sorted(zip(window, scores),
                          key=lambda pair: float(pair[1]), reverse=True)]
                ranked = window + [key for key in ranked if key not in set(window)]
                reranked = True
            except Exception as exc:
                errors.append("reranking failed; using fused order")
                _index_state["last_search_error"] = str(exc)
        else:
            errors.append("reranking unavailable; using fused order")
    chosen = br.select_notes(ranked, pool, k)
    results, seen = [], set()
    for key in chosen:
        p = pool[key]
        doc = br.identity(p["root"], p["path"])
        note = notes[doc]
        seen.add(doc)
        warnings = bm.memory_warnings(note["metadata"]) + errors
        if doc in superseded:
            warnings.append("superseded by " + ", ".join(": ".join(x) for x in superseded[doc]))
        results.append({"source": p["path"], "root": p["root"], "path": p["path"],
                        "snippet": br.note_excerpt(p["evidence"], note, q),
                        "score": round(float(doc_fused[doc]), 5),
                        "via": "+".join(m for m, order in (("vector", doc_vorder), ("lexical", doc_lorder), ("title", title_order)) if doc in order),
                        "reranked": reranked, "metadata": note["metadata"], "warnings": warnings,
                        "mode": mode})
    if use_expand:
        added = 0
        for result in list(results):
            source = br.identity(result["root"], result["path"])
            for target in notes[source]["links"]:
                doc = br.resolve_link(target, source, notes)
                if doc is None:
                    result["warnings"].append(f"unresolved or ambiguous link: {target}")
                    continue
                if doc in seen or doc not in allowed:
                    continue
                note = notes[doc]
                results.append({"source": note["path"], "root": note["root"], "path": note["path"],
                                "snippet": br.excerpt(note["body"], q), "score": 0.0,
                                "via": "link", "linked_from": result["path"], "reranked": False,
                                "metadata": note["metadata"], "warnings": bm.memory_warnings(note["metadata"]),
                                "mode": mode})
                seen.add(doc)
                added += 1
                if added >= k:
                    break
            if added >= k:
                break
    return results


# --- HTTP ------------------------------------------------------------------

app = FastAPI(title="Obsidian RAG Indexer", version=br.VERSION)


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
    out = {"status": "ok", "version": br.VERSION,
           "capabilities": ["unique-notes", "prefilter", "current-history", "qualified-links", "body-excerpts"],
           "index_state": dict(_index_state), "model": EMBED_MODEL, "dim": EMBED_DIM,
           "rerank": RERANK, "default_exclude": list(DEFAULT_EXCLUDE),
           "lex_docs": len(LEX_DOCS), "links": sum(len(n["links"]) for n in list(NOTE_META.values())),
           "pending_index": len(_watcher_handler._pending) if _watcher_handler else 0,
           "pending_delete": len(_watcher_handler._deleted) if _watcher_handler else 0,
           "watcher_active": _watcher_handler is not None, "by_root": {}, "chunks": 0}
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
           roots: str = "", rerank: str = "", expand: str = "", candidates: str = "", mode: str = "current"):
    try:
        return do_search(q, k=k, include=include, exclude=exclude, roots=roots,
                         rerank=(rerank or None), expand=(expand or None),
                         candidates=(candidates or None), mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    global _watcher_handler
    _ensure_dim()
    per_root, embedded, skipped, purged = full_scan()
    print(f"[rag] ready: {per_root}, embedded {embedded}, skipped {skipped}", flush=True)
    handler = VaultHandler()
    _watcher_handler = handler
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
