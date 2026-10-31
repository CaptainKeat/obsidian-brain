# Connected project memories and safe upgrades

Obsidian's native graph draws internal links. Similar wording, a `project:` value,
tags, source paths and chat IDs do not create note-to-note edges. Graphify/Atlas
semantic relationships are a separate graph. Showing orphans or unresolved targets
can therefore expose many disconnected dots even when semantic recall works.

Typed saves now create a stable navigation hub for an explicit nonempty `project`
label and link the memory to it. Hubs use label hashes to prevent slug collisions;
case variants share a key, while different labels/workstreams remain separate.
No project assignment is inferred from topical similarity. Related-note links are
added only for existing, unambiguous vault destinations in `sources`/`supersedes`.
Raw metadata identities, including Brain `vault:`/`projects:` references, remain
unchanged. Visible body links use ordinary vault-relative Obsidian paths.

Legacy saves repair exact known visible links and reuse existing explicit project
metadata when present. They cannot infer a project from an unstructured chat. Prefer
typed saves with `project`, and supply verified existing checkpoint paths in
`sources`. The optional legacy REST route normalizes body links but does not create
project assignments; use the typed writer for project hubs and guarded revisions.

## Update an existing installation

1. Back up the checkout/config and keep your existing vault, state, DB and models.
   Review local code changes before pulling; do not overwrite a customized checkout.
   Pull this repository's update, install the existing pinned requirements if needed,
   then run `python scripts/sync_skill.py --apply`. Use repeated `--target` options
   for other skill installations. Merge the updated project-instruction template
   without replacing your project's instructions or write policy.
2. Reconnect each Brain MCP client so its long-lived Python writer imports the new
   module. No MCP argument schema changes or embedding-model/index rebuild is needed.
   The HTTP indexer need not restart for this writer fix. Its vault watcher sees note
   changes; verify health and a source read rather than trusting counts alone.
3. Preview the optional historical-note repair. Supply your own paths:

   ```powershell
   python scripts/repair_graph_links.py --vault "C:\MyVault" --report "C:\BrainRepair\preview.json"
   ```

   Inspect `repairs`, `unresolved` and planned hub labels. The report can contain note
   text; keep it private and outside indexed/project roots. The tool does not rename,
   merge or delete existing notes, change graph settings, infer fuzzy matches, or
   import Graphify-generated notes. Code, YAML metadata and revision-metadata records
   are protected. Unique stored titles can identify legacy filename mismatches;
   ambiguous/missing destinations stay unchanged.
4. Apply with a fresh backup directory **outside the vault and other indexed roots**:

   ```powershell
   python scripts/repair_graph_links.py --vault "C:\MyVault" --apply --backup-dir "C:\BrainRepair\run-001"
   ```

   All originals are backed up before the first note edit. Hash checks plus Brain
   note locks detect cooperating/concurrent changes. A conflict is reported with
   exit code 2; inspect the receipt and rerun a new preview. Avoid editing the same
   notes in Obsidian during migration: external editors do not share Brain's locks.
   Run the preview again afterward; unchanged inputs should produce zero edits.
5. Open `Brain Project Map.md`, follow a hub and open its local graph/Backlinks.
   Confirm representative checkpoint/session links resolve to real notes. Hiding
   orphans or enabling Existing files only is optional visual cleanup, not a repair.
   Review the unresolved list manually; do not create empty notes to silence it.
   After a large batch of external file changes, Obsidian can miss new-file events.
   If a verified file exists but the link offers to create it, save any open edits
   and use Obsidian's **Reload app without saving** command before checking again.
   Do not create a duplicate file from the unresolved link.

## Roll back

```powershell
python scripts/repair_graph_links.py --rollback "C:\BrainRepair\run-001\receipt.json"
```

Rollback verifies backup hashes and restores original bytes, including encoding and
newlines. Only exact migration-created files are removed. Later user/agent edits
are preserved and reported as rollback conflicts. Keep the receipt and backups;
never apply an old receipt against another vault. Restore code from its separate
backup and reconnect MCP clients if reverting the writer as well.

Synthetic regression tests cover hub creation, metadata identity retention,
qualified/unique-title repairs, ambiguous targets, traversal/cross-root refusal,
protected code/metadata, idempotence, and concurrent-edit-safe rollback. They do not
establish Obsidian runtime cache behavior on every platform.
