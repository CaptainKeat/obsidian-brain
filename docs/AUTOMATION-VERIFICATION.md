# Automation verification — October 30, 2026

Cross-project update later the same day: all **64 current backend/setup tests**
passed, including two new retrieval/provenance/scope checks and the updated
generated-instructions contract. The read-only live HTTP demo retrieved the same
Sample Alpha lesson at rank 1 from both Alpha and Beta caller directories, then
read its complete synthetic source. The original sample recall also remained rank 1.
This confirms shared retrieval and source reading, not autonomous-agent behavior.
The unchanged 26 Atlas checks last passed in the baseline run below. The baseline
counts and runtime observations below describe the earlier automation release.

The portable release was tested on Windows with Python 3.11, using disposable
vaults, project docs, vector databases, model views and ports. The installed private
Brain/Atlas and their existing scheduler task were left running and unchanged.

## Automated checks

- **62 Brain and automation tests passed**, including 18 new checks for no-op
  refresh, content changes with unchanged mtimes, source deletion, missing-output
  repair, extraction/source coverage, private/generated exclusions, concurrent
  source changes, failed promotion rollback, configuration boundaries, supervisor
  ownership, guarded digest replacement and preventing duplicate MCP startup.
- **26 Atlas tests passed** for source revisions, queues, control APIs, pause,
  recovery and the companion supervisor.
- All **88 tests passed in a newly created virtual environment**, with no inherited
  system-site packages. The first unconstrained install exposed MCP 2.x removing
  FastMCP. Compatible core/model versions were pinned, installed into that isolated
  environment and retested. `pip check` then reported no broken requirements.

Key tested versions: Python 3.11; torch 2.12.1+cpu; MCP 1.28.0; LanceDB 0.33.0;
PyArrow 24.0.0; sentence-transformers 5.6.0; transformers 5.6.1; tokenizers 0.22.2;
huggingface_hub 1.27.0; Graphify 0.5.7; Laya 0.3.6. Core versions are in
`requirements.txt`; Graphify and Laya are pinned in their respective requirement files.

## Real startup and scheduling

The installer registered three uniquely named, temporary Windows tasks and started
their actual actions. Exported XML confirmed per-user InteractiveToken/least
privilege, a 20-second sign-in delay, daily 03:00 local graph trigger, duplicate
suppression, supervisor restart policy and correctly quoted paths containing spaces.

The scheduler-owned Brain and Atlas listeners returned the configured instance
identity. The daily graph task completed with Windows result **0**. Adding one
synthetic source and starting that task again extracted only the changed note,
rebuilt the graph and retained a backup. An unchanged run performed **zero semantic
extractions**. These were real authenticated Codex CLI calls and real Graphify
rendering, not an extraction stub.

Stopping only the verified sample Atlas worker caused its scheduled supervisor to
launch a replacement while retaining all three source-hash records. A first fixture
assertion expected an exact row count while another test added a legitimate new
note; the fixture was corrected to check retention of existing rows and rerun.
Recovery passed with a stable three-note fixture. An intentional shutdown then
preserved pause, prevented supervisor relaunch and retained all three raw results.

The task remover unregistered only that temporary installation. Both test listeners
were confirmed stopped. The pre-existing private Brain stayed healthy and its Atlas
task remained running. No actual Windows reboot or sign-out was performed: task
registration, triggers, task-launched processes, recovery and removal were tested.

## Fresh-environment runtime

The fresh environment started a separate Brain with the **default all-MiniLM-L6-v2**
model and an isolated new cache/database. All three synthetic documents were indexed;
scoped current-mode recall returned the sample project at rank 1. The guarded-memory
demo rejected an outdated hash. The packaged readiness checker passed, including
CLI login, package versions, matching service identities and model readiness.

Atlas in that fresh environment loaded the pinned local Laya revision and completed
two real sample classifications: `device=cpu`, two Torch threads,
`cuda_initialized=false`, BelowNormal Windows priority. Existing pinned weights were
copied into an independent model view; the optional first-time weight downloader
was not exercised. The runtime reported an upstream temperature-clamping warning;
scores remain explicitly uncalibrated and classification quality was not evaluated.

Semantic extraction and Graphify generation also passed from the fresh environment.
A second run skipped extraction. An additional scheduled test published a generated
Brain Map into a disposable vault, excluded it from subsequent extraction, and
confirmed it became searchable through the Brain watcher.

## Limits

This verifies the documented Windows path, not every PC, Python version, client or
dependency combination. The graph runner currently covers admitted vault Markdown;
other Graphify input types remain manual. Authentication, model-provider access and
usage limits belong to the installing user's Codex account. The runner follows the
same semantic/Graphify roles as the original desktop automation, using Task Scheduler
and CLI execution instead of an app-specific heartbeat and notification inbox.
The generated digest is a source-linked navigation summary, not a verified narrative
of all project facts. Read canonical notes before acting on graph/model suggestions.
