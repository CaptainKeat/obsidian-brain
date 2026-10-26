"""
brain_search.py — pure-Python search helpers for the Obsidian RAG brain.

No heavy deps (no torch / lancedb / sentence-transformers), so this module is
import-safe and unit-testable on its own. rag_indexer.py imports it to add:

  - BM25 lexical scoring            (hybrid keyword+vector search, #4)
  - reciprocal-rank fusion          (merge vector + lexical rankings)
  - wikilink parsing + link graph   (graph expansion over [[links]], #6)
  - folder include/exclude filters  (namespace/folder scoping, #2)

Everything here is deterministic and side-effect free.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

# --- tokenization ----------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")
# a small, generic stoplist — keep it short so technical terms survive
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "be", "it", "this", "that", "with", "as", "at", "by", "from", "we", "you",
    "i", "if", "so", "but", "not", "no", "do", "does",
}


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens, minus a tiny stoplist. Keeps short acronyms."""
    if not text:
        return []
    words = [t for t in _WORD.findall(text.lower()) if t not in _STOP and len(t) > 1]
    # Drive letters carry identity in Windows setup recall; do not discard them
    # as generic one-letter words. Match both D:\\ and "D-drive" / "D drive".
    drives = re.findall(r"\b([a-z])(?=:|[\s-]+drive\b)", text.lower())
    return words + ["drive_" + letter for letter in drives]


# --- BM25 (Okapi) ----------------------------------------------------------

class BM25:
    """Minimal Okapi BM25 over a list of pre-tokenized documents.

    Rebuild whenever the corpus changes. score(query) returns a list of floats
    aligned to the document order passed to build().
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[list[str]] = []
        self.doc_len: list[int] = []
        self.avgdl: float = 0.0
        self.df: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.tf: list[dict[str, int]] = []

    def build(self, tokenized_docs: list[list[str]]) -> "BM25":
        self.docs = tokenized_docs
        self.doc_len = [len(d) for d in tokenized_docs]
        n = len(tokenized_docs)
        self.avgdl = (sum(self.doc_len) / n) if n else 0.0
        self.df = {}
        self.tf = []
        for d in tokenized_docs:
            freqs: dict[str, int] = defaultdict(int)
            for t in d:
                freqs[t] += 1
            self.tf.append(dict(freqs))
            for t in freqs:
                self.df[t] = self.df.get(t, 0) + 1
        # idf with the standard BM25 +0.5 smoothing, floored at a small positive
        self.idf = {}
        for t, df in self.df.items():
            self.idf[t] = max(1e-6, math.log((n - df + 0.5) / (df + 0.5) + 1.0))
        return self

    def score(self, query: str | list[str]) -> list[float]:
        q = query if isinstance(query, list) else tokenize(query)
        if not self.docs or not q:
            return [0.0] * len(self.docs)
        scores = [0.0] * len(self.docs)
        for i, freqs in enumerate(self.tf):
            dl = self.doc_len[i] or 1
            s = 0.0
            for t in q:
                f = freqs.get(t)
                if not f:
                    continue
                idf = self.idf.get(t, 0.0)
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                s += idf * (f * (self.k1 + 1)) / denom
            scores[i] = s
        return scores

    def top_n(self, query: str | list[str], n: int) -> list[tuple[int, float]]:
        scored = list(enumerate(self.score(query)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(i, s) for i, s in scored[:n] if s > 0.0]


# --- rank fusion -----------------------------------------------------------

def reciprocal_rank_fusion(rankings: list[list], k: int = 60) -> dict:
    """Reciprocal Rank Fusion. `rankings` is a list of ranked id-lists (best first).
    Returns {id: fused_score}. Robust to lists of different lengths/overlap."""
    fused: dict = defaultdict(float)
    for ranking in rankings:
        for rank, _id in enumerate(ranking):
            fused[_id] += 1.0 / (k + rank + 1)
    return dict(fused)


# --- wikilinks / graph -----------------------------------------------------

_WIKILINK = re.compile(r"\[\[([^\]]+?)\]\]")


def _slug(name: str, maxlen: int = 60) -> str:
    """Mirror vault_writer._slug so link targets resolve to note slugs."""
    s = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    s = re.sub(r"[\s_]+", "-", s)
    return (s[:maxlen] or "note").strip("-")


def parse_wikilinks(text: str) -> set[str]:
    """Return the set of link targets (as slugs) referenced by [[Target|alias]]."""
    out = set()
    for m in _WIKILINK.findall(text or ""):
        target = m.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            out.add(_slug(target))
    return out


def path_to_slug(path: str) -> str:
    """Slug of a note from its vault-relative path (filename without .md)."""
    base = re.split(r"[\\/]", path)[-1]
    if base.lower().endswith(".md"):
        base = base[:-3]
    return _slug(base)


# --- folder / namespace filters --------------------------------------------

def _norm(p: str) -> str:
    return (p or "").replace("\\", "/").lower().strip("/")


def folder_match(path: str, include=None, exclude=None) -> bool:
    """True if `path` passes include/exclude folder filters.

    include/exclude are iterables of folder-name or path-prefix fragments
    (case-insensitive). A path matches a fragment if any of its segments equals
    the fragment or the normalized path startswith it.
    """
    np = _norm(path)
    segs = set(np.split("/"))

    def hit(frag):
        f = _norm(frag)
        return f in segs or np.startswith(f + "/") or np == f

    if exclude:
        if any(hit(f) for f in exclude):
            return False
    if include:
        return any(hit(f) for f in include)
    return True


def parse_csv_param(val) -> list[str]:
    """Parse a comma-separated query param into a clean list (or [])."""
    if not val:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if str(x).strip()]
    return [p.strip() for p in str(val).split(",") if p.strip()]
