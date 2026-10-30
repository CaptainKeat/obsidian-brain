# How the second-brain stack fits together

| Layer | Job | Start here |
| --- | --- | --- |
| Your Markdown vault | Canonical notes, project checkpoints and evidence | Use your own Obsidian vault or `examples/vault` |
| Obsidian Brain | Hybrid retrieval, full-note reads, typed memory and guarded revisions | [Main setup](../README.md) |
| Assistant skill | Recall before rediscovery, read source notes, save useful evidenced learning | [Skill](../cowork-skill/SKILL.md) |
| Graphify (separate upstream project) | Generate a navigable relationship graph | [Graphify integration](GRAPHIFY.md) |
| Neural Atlas | Visual exploration, source hashes and optional CPU triage | [Atlas setup](../neural-atlas/README.md) |

Start with Brain and the included sample vault. Add the assistant skill once the
MCP tools work. Add Graphify and Atlas when graph navigation is useful. The Brain
does not depend on either companion, and Atlas suggestions do not change search
results or canonical notes.

For automatic background operation, follow [Windows startup and daily refresh](AUTOMATIC-SETUP.md).

## Everyday workflow

1. Search the project identity and concrete problem before exploring the code again.
2. Read the full matching checkpoint, especially its latest applicable revision.
3. Verify volatile facts against current source, running state or external evidence.
4. Do the authorized work and retain useful evidence.
5. Save meaningful decisions, fixes, failed attempts and checkpoints with sources.
6. Read substantive writes back. Reconcile hash conflicts instead of overwriting.

Search `mode=current` hides explicitly stale/expired/superseded notes. It does not
certify every remaining fact. Use `mode=all` for history and conflicting evidence.
Graph edges, ranks and model scores are navigation aids. Source claims still need
appropriate verification.

## Bring your own data

The shared repo contains source code and synthetic fixtures. Use ignored local
configuration for your own vault, project docs, models and indexes. Keep generated
graph/wiki output and Atlas databases outside the canonical vault. A generated
digest can be useful if it is clearly dated, source-linked and reviewed.

No personal vault, original conversation history, vector database, Atlas revision
database, model weights, machine scheduler entries or credentials are included.
