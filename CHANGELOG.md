# Release notes

## 2026-10-30 · second-brain source refresh

- Updated retrieval and typed-memory engine: server 3.0.3, compatible MCP 3.0.0
  schemas, history, qualified links, retained revisions, lexical fusion and excerpts.
- Added portable skill 4.0.0, explicit-target installer and read-only recall checks.
- Added Neural Atlas 0.1 source/tests, portable configuration and CPU setup guidance.
- Fixed first-run sample retrieval: chunking now retains short paragraphs/headings
  and exact contiguous source text instead of joining nonadjacent paragraphs that
  the source-evidence validator correctly rejected. Three focused regressions
  failed before the fix and pass afterward. Existing installations should select
  a fresh `DB_PATH` once when upgrading to rebuild vectors with the new chunks;
  ordinary `/reindex` skips unchanged files. Preserve the old database for recovery.
- Documented the full stack and separate upstream Graphify integration.
- Retained synthetic defaults and public Git history. Private vaults, indexes,
  logs, weights, scheduler records and local machine paths are excluded.

Validation of the public snapshot:

- 44 Brain tests and 26 Atlas tests passed using temporary synthetic files.
- A separate HTTP indexer at server 3.0.3 indexed all three sample documents;
  current-mode sample project recall passed at rank 1, with no duplicates or
  empty/metadata-only excerpts. It reused cached BGE CPU embeddings in an existing
  environment; this was not a fresh dependency install or default-model download.
- MCP health, scoped search and complete source reading passed against that
  isolated indexer. The disposable memory demo rejected a stale revision hash.
- The actual Atlas browser loaded the sample graph, selected a node, displayed its
  full source and SHA-256, and returned the sample project through Brain search.
  A screenshot was inspected; the browser reported no console warnings/errors.
- Optional Laya inference was not freshly exercised for this publication. Missing
  weights are reported by the demo worker; graph/source/search remain available.

The working private Brain and Atlas were not upgraded or restarted for this release.
