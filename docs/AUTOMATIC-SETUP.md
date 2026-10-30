# Automatic startup and daily graph refresh on Windows

This packages the same roles used by the local stack: a background Brain, a CPU-only
Atlas companion, and an AI-assisted daily Graphify rebuild. The portable scheduler
uses Windows Task Scheduler and the Codex CLI, so it does not require keeping the
Codex desktop app or a browser open. No administrator account or stored password
is required. Tasks run as the installing user after sign-in.

## 1. Install dependencies

Install Python 3.11/3.12, clone this repository, and open PowerShell in the checkout.
Use a dedicated environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-automation.txt
```

Install and sign into the [Codex CLI](https://learn.chatgpt.com/docs/cli/reference)
using its official instructions. Confirm `codex --version` and `codex login status`
in your user session. Semantic extraction uses the CLI's configured model/account
and its usage limits. Selected note text is sent to that configured model provider;
the vector index and Atlas CPU inference remain local. No API key belongs in this repo.

Optional Laya CPU triage uses the pinned runtime and separately licensed weights:

```powershell
.\.venv\Scripts\python.exe -m pip install -r neural-atlas/requirements.txt
.\.venv\Scripts\python.exe scripts/download_laya.py --destination "C:/Models/laya-brain"
```

The helper explicitly downloads revision `1c5edc17a7acd8701df6fc341c0d179f1c62c982`.
It does not run at startup. Review the [upstream model/license](https://huggingface.co/convaiinnovations/laya/tree/1c5edc17a7acd8701df6fc341c0d179f1c62c982).
Without weights, graph browsing and Brain search still work; triage reports unavailable.

## 2. Configure your paths

Use your own existing vault and a separate folder containing project docs. Keep
generated state outside both roots. Do not point the project root at this whole
checkout if state is inside it. Example paths below are placeholders:

```powershell
.\.venv\Scripts\python.exe scripts/setup_stack.py `
  --state "C:/BrainState" `
  --vault "C:/Notes/MyVault" `
  --projects "C:/ProjectNotes" `
  --model-path "C:/Models/laya-brain" `
  --digest-path "Cowork/Projects/brain-map.md"
```

Omit `--model-path` if skipping triage. Omit `--digest-path` to keep all generated
output outside the vault. With that option, the one reserved generated note is
updated after verified refreshes, preserving frontmatter and rejecting concurrent
edits through SHA-256 checks. It is excluded from extraction to avoid feedback.
If `codex` is not on PATH, add
`--codex "C:/path/to/codex.exe"`. You may provide separate `--graph-python` or
`--atlas-python` environments and distinct `--brain-port` / `--atlas-port` values.
The default ports are 5180 and 5190. The configurator refuses to overwrite an
existing installation. Edit its private `stack.json` and `atlas/config.json` for
later setting changes; stop the affected tasks first.

This creates local configuration, an independent Atlas runtime and private state
directories. When model files are supplied, small configs/tokenizer are copied and
weights are hardlinked or copied into Atlas state so it does not modify the model
configuration used by another app. Only an explicitly configured generated digest
is written into the vault; all other source notes remain read-only.

The configurator also writes `mcp-server.json` with your actual Python, adapter,
vault, project root and endpoint. Merge that server entry into your MCP client's
configuration using its supported format; do not replace unrelated servers.
It disables the adapter's batch-file auto-start so the supervisor is the sole
startup owner. Then install the assistant skill:

```powershell
.\.venv\Scripts\python.exe scripts/sync_skill.py --apply
```

That command targets Codex by default. Use `--target <directory>` for another
client. Configure your own memory-write preference; personal permissions are not
copied from this repository's author. Reconnect the MCP client after changing its
server configuration and verify `obsidian_health` plus a known-note search.

For multiple projects, reuse this same MCP server entry and shared vault. Merge
the generated `<state>/PROJECT-INSTRUCTIONS.md` into each project's `AGENTS.md`.
The installed skill now explicitly searches shared problem patterns across project
boundaries and verifies transfers before saving target-project outcomes. See the
[README cross-project workflow](../README.md#cross-project-learning-use-one-shared-brain).

## 3. Run and verify the first graph

```powershell
.\.venv\Scripts\python.exe scripts/graph_refresh.py --config "C:/BrainState/stack.json"
```

This must finish with `status=refreshed` before installing an unattended schedule.
Output is in `C:/BrainState/graph/graphify-out`: `graph.json`, `graph.html`,
`GRAPH_REPORT.md`, a dated `BRAIN_MAP.md`, generated Obsidian notes and wiki pages.
Atlas uses that graph automatically. Keep these generated trees outside your vault.
The dated map is a derived navigation aid; canonical claims still require sources.

Unchanged notes reuse the previous extraction by SHA-256. No change means no AI
request and no rewrite of the published graph. Changed Markdown is processed in
bounded batches; deletion removes that source's concepts and dangling edges. Every
source must be represented, every edge must have valid endpoints/provenance, and
source hashes must still match after extraction. Any failed batch, changed source
or missing output prevents publication. A previous generation is retained as a
backup; a failed promotion restores it. Review `graph-status.json` on failure.

The refresh covers admitted vault Markdown. It excludes hidden directories,
generated Graphify material, VTuber-Memory, sensitive filenames/directories and
frontmatter `private: true`, `atlas_exclude: true` or `graph_exclude: true`.
These are explicit filters, not a guarantee of detecting every private datum.
Sources over 1 MiB stop the refresh instead of being silently truncated. Other
Graphify input types can be processed manually with the upstream tool.

## 4. Install Windows tasks

Preview the exact task XML without registering anything:

```powershell
powershell -NoProfile -File scripts/windows-tasks.ps1 -Config "C:/BrainState/stack.json" -PlanOnly
```

Register and start the stack:

```powershell
powershell -NoProfile -File scripts/windows-tasks.ps1 -Config "C:/BrainState/stack.json" -DailyAt 03:00 -Start
.\.venv\Scripts\python.exe scripts/check_stack.py --config "C:/BrainState/stack.json"
```

Three tasks get a unique ID derived from your configuration path:

| Task | Trigger and behavior |
| --- | --- |
| Brain | 20 seconds after sign-in; background supervisor with crash recovery |
| Atlas | 20 seconds after sign-in; CPU-only worker with crash recovery and persistent pause |
| Graph | Daily at 03:00 in **your Windows local timezone**; missed runs start when available |

They use InteractiveToken/least privileges, hidden Python, duplicate suppression,
and the actual absolute paths configured on your PC. Brain/Atlas supervisors poll
every 30 seconds, with a 120-second launch backoff. A slow model load is allowed
to finish; it cannot trigger duplicate workers. A foreign listener on a chosen
port is reported and left alone. A persistent stop marker prevents relaunch.

Close the browser and desktop app normally. Background tasks remain independent.
Open <http://127.0.0.1:5190> for Atlas. On a new sign-in, startup is delayed 20 seconds.
The PC must be powered on and signed into your Windows account. Sleep suspends work;
the scheduler catches up when available. This does not install a pre-login service.

## Status, pause, recovery and removal

`check_stack.py` checks package versions, Codex availability/login, endpoint identity, graph run status and
whether the configured weights exist. Actual Laya readiness appears in Atlas status;
weights existing on disk alone does not prove a successful model load. Logs are
`brain.log`, `atlas.log`, `brain-status.json`, `atlas-status.json`, `graph-status.json`
and per-run graph logs under the state directory. They may contain note text or
model output; keep the whole state directory private.

Use Atlas Pause to stop classification without losing history. An intentional
Atlas shutdown preserves pause so the supervisor will not undo it. To stop Brain
or Atlas and its owned worker, create `brain.stop` or `atlas.stop` in the state
directory; the supervisor notices promptly. Remove that marker and start the
corresponding task to resume. A paused Atlas still needs Resume in its interface.

To unregister only this installation's tasks:

```powershell
powershell -NoProfile -File scripts/windows-tasks.ps1 -Config "C:/BrainState/stack.json" -Remove
```

Removal retains notes, configuration, model files, graph backups and Atlas history.
Task-name collisions with a different ownership marker are rejected. Do not delete
state to resolve a model or login error. Authenticate the CLI in your own user
session, run a manual refresh, then check the task result.

## Tested scope

See [AUTOMATION-VERIFICATION.md](AUTOMATION-VERIFICATION.md) for the actual published
verification, including real task registration/launch and semantic extraction.
Tests do not imply that a reboot was performed or that every dependency combination
has been validated. The existing installed private stack is separate from this release.
