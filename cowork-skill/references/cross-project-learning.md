# Cross-project learning

The shared Brain indexes the configured vault and project-document collection.
The current working directory is not a search boundary. Configure every client
with the same endpoint and roots; separate per-project indexes cannot share their
notes automatically.

For a new task in Sample Beta, first recall Beta's current checkpoint. Then search
`worker crash recovery persistent pause` in the shared vault's pattern folders.
Read the full result from Sample Alpha even though the project names differ.
Compare platform, process ownership, launcher behavior and pause semantics. Test
the transferred approach in Beta before describing it as successful there.

For the included synthetic vault, these are MCP tool calls, not shell commands:

```text
obsidian_search(query="Sample Beta", roots="vault", include="Projects", mode="current")
obsidian_search(query="worker crash recovery persistent pause", roots="vault", include="Patterns,Gotchas,Examples", mode="current")
obsidian_get_note(path="Cowork/Patterns/owned-worker-recovery.md", root="vault")
```

Folder names are conventions, not a required schema. Broaden the second query if
an older useful lesson lives elsewhere. Do not leave Beta's project-folder filter
on the cross-project query. `project` metadata records provenance; it does not
prevent another context from retrieving that lesson.

Save a separate reusable lesson only when it adds value, with the originating
project, actual evidence/sources, applicability, limitations and what failed.
Keep target-specific settings in its own checkpoint. Links preserve both the
general lesson and the project context without duplicating whole checkpoints.
Use a fresh hash when revising an existing lesson.

The repository's `templates/PROJECT-AGENTS.md` can be merged into participating
projects' AGENTS.md files. The setup helper also copies it to the private state
directory as PROJECT-INSTRUCTIONS.md. The owner chooses the write-back policy;
the template does not carry the author's personal authorization.

Graphify helps discover connections and Atlas helps review suggestions. Neither
automatically proves transfer or copies all conversations into every agent context.
Actual reuse still depends on retrieval, verification and meaningful saves. A
shared Brain exposes its admitted notes to connected clients: filters are not
security boundaries. Separate sensitive projects into a different vault/Brain.
