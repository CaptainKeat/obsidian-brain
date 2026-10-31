# Brain maintenance

Skill source is `cowork-skill/` in this checkout. Run `python scripts/sync_skill.py`
to check the default Codex installation, or provide repeated `--target` directories.
`--apply` installs changes with backups, preserving unrelated files. Plugin updates
can overwrite cached copies.

Run `python -B -m unittest discover -s tests -v` for implementation changes. Tests
use temporary synthetic vaults and model-free retrieval doubles. Use
`scripts/check_recall.py --cases <json> --report <new-path>` for read-only live
known-answer checks. Keep reports outside indexed roots; supply the service's root
environment variables. Curated recall does not establish universal answer quality.

Vault notes are watched; project docs refresh at startup or POST `/reindex`.
Counts and mtimes do not prove indexed freshness. After schema changes, reconnect
only the affected MCP client. After HTTP implementation changes, restart only its
verified listener when authorized. Do not restart healthy services or replace
embedding models to compensate for query-usage issues.

For native Obsidian links, see [graph link repair](graph-links.md).
