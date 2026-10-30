# Graphify integration

[Graphify](https://github.com/Graphify-Labs/graphify) is a separate upstream project.
It is not vendored or relicensed here. Follow its current install instructions and
license; the Python distribution is `graphifyy` (two y's).

The upstream workflow installs the CLI (for example, `uv tool install graphifyy`),
registers its assistant skill with `graphify install`, then uses `/graphify <path>`
inside a supported assistant. Check its current command help before running a
refresh; command availability and output schema can change between versions.

Build your own graph from approved notes. Keep generated `graphify-out/`, `obsidian/`
and `wiki/` trees outside the source vault or explicitly exclude them from detection
to avoid indexing generated summaries as independent evidence. Exclude sensitive
material before extraction and consider the configured assistant's data handling.

Neural Atlas reads the resulting `graph.json` path from its local `config.json`:

```powershell
python neural-atlas/configure.py --vault "C:/Notes/MyVault" --graph "C:/BrainMap/graphify-out/graph.json"
```

The Atlas importer accepts Graphify `nodes` with source-file references and either
`links` or `edges`. It only admits concepts whose Markdown source maps into its
configured vault. Check Atlas status for importer errors and schema incompatibility.
The included [tiny graph](../examples/graph.json) is synthetic and illustrates a
source reference; it is not an export of anyone's knowledge base.

For incremental refreshes, preserve the previous snapshot, compare supported-source
hashes, extract only changed material using the upstream workflow, and check source
coverage plus errors before replacing the output. Leave unchanged snapshots alone.
Rebuilds and refresh scheduling are independent of the Brain and Atlas workers.

Treat `EXTRACTED`, `INFERRED` and `AMBIGUOUS` labels as provenance, not verification.
Import-time hashes cannot reconstruct a source's historical contents. Read the
current canonical note before accepting an important relationship or writing back.
