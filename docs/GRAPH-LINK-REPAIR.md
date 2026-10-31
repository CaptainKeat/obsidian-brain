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

## Copy this prompt to your AI agent

Replace placeholders with discovered, verified paths. This prompt authorizes local
updates and reversible repairs; it does not authorize publishing private data.

```text
Update my existing Obsidian Brain installation and safely reconcile its old native
Obsidian linking issues. I authorize verified local code/skill updates, external
backups, and reversible repairs within my actual vault. Proceed with clear cases;
leave ambiguous relationships unchanged and report them.

1. Locate the real active vault, Brain checkout, configured Python environment,
   indexed roots, MCP clients and installed skill copies. Read applicable local
   instructions. Verify the checkout's remotes against
   https://github.com/CaptainKeat/obsidian-brain; preserve legitimate forks and
   custom configuration. Inspect Git status and local changes before updating.
   Back up code/config first. Use a fast-forward update only when safe; do not
   reset, force-pull, discard changes, switch remotes or overwrite customizations.

2. Read docs/GRAPH-LINK-REPAIR.md in the updated checkout. Use the installation's
   configured Python environment and existing pinned dependencies. Run:
   python -B -m unittest discover -s tests -v
   Install the updated skill with:
   python scripts/sync_skill.py --apply --target "<SKILL_DIR>"
   Repeat --target for each verified installation. Preserve unrelated files,
   project instructions and my memory-write policy. Merge relevant template
   guidance instead of replacing existing project instructions.

3. Create a private repair directory outside the vault AND every indexed root.
   Resolve all placeholders to real absolute paths. Preview without editing:
   python scripts/repair_graph_links.py --vault "<VAULT>" --report "<REPAIR_DIR>/preview.json"
   Inspect planned changes, hub labels, exact destination mappings and unresolved
   targets. The report can contain note text: keep it local and private.

4. Repair only explicit project assignments and existing, unambiguous links.
   Preserve project/version/workstream identities, note bodies, metadata, chat
   references and historical claims. Do not infer relationships from similar
   wording alone. Do not rename, merge or delete existing notes; create empty
   target notes; import generated Graphify notes; or change graph settings.
   Keep ambiguous/missing mappings unchanged. Avoid simultaneous editing of the
   affected notes. Apply verified repairs with a fresh backup directory:
   python scripts/repair_graph_links.py --vault "<VAULT>" --apply --backup-dir "<REPAIR_DIR>/run-001"
   Keep all original backups and receipt.json. If hashes conflict or execution
   is interrupted, inspect the receipt and actual file hashes before retrying.
   Use a fresh preview and backup directory for remaining changes; never blindly
   repeat writes or overwrite later user/agent edits. Preserve every receipt.

5. Reconnect affected Brain MCP clients so they load the updated writer. Coordinate
   reconnects with active work; do not kill unrelated processes. Do not rebuild
   databases, change embedding models, or restart the HTTP service solely for this
   writer update. Check health, watcher errors and pending indexing; do not equate
   a healthy endpoint with complete index freshness.

6. Run another preview: unchanged inputs should propose zero edits. Verify raw
   metadata identities and historical content are preserved and every new
   navigation destination exists. In Obsidian open Brain Project Map.md, follow
   representative project/session/checkpoint links, and check hub Backlinks and
   the local graph. If an existing file offers to be created, save any open edits
   and reload Obsidian's cache with Reload app without saving, then recheck.
   Do not bypass security warnings or claim runtime checks you could not perform.

7. Report the before/after code revision, files and link/hub counts, exact tests,
   remaining ambiguous mappings, index backlog, client reconnects and limits.
   Give backup/receipt paths and rollback instructions:
   python scripts/repair_graph_links.py --rollback "<REPAIR_DIR>/run-001/receipt.json"
   For multiple runs, roll back receipts newest first. Rollback must preserve
   later edits as conflicts. Do not run rollback unless needed or requested.

Do not upload or publish my vault, raw chats, credentials, indexes, databases,
models, backups or repair reports. Do not push Git commits. If a required action
is denied or needs approval, stop that action, explain the exact blocker and
continue independent safe work; never bypass the restriction.
```
