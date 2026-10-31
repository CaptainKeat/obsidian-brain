# Native graph links

Use the exact explicit project label on typed memory saves. The writer creates a
stable hub and adds existing vault-note sources as body links while retaining raw
metadata identities. Ordinary note prose must link to an existing vault-relative
path, optionally using display text; do not paste Brain `vault:` namespaces as
Obsidian targets. Never infer graph edges from chat IDs, source paths or tags.

For an authorized repair, use `scripts/repair_graph_links.py` from the Brain
checkout. It is read-only by default; inspect its report, then apply with a fresh
backup directory outside indexed roots. It repairs exact paths/unique saved titles,
leaves ambiguous links untouched and retains historical bodies. Rollback uses the
receipt, verifies hashes and refuses to overwrite later edits. Consult
`docs/GRAPH-LINK-REPAIR.md` for commands and limits. Do not change graph settings or
run bulk migration without the owner's instruction.

After updating code, reconnect affected MCP clients so the long-lived writer loads
it. No embedding-model/database rebuild or HTTP service restart is required for
this change. Verify readback, a representative existing destination, hub Backlinks
and local graph. Counts alone do not prove Obsidian runtime resolution.
