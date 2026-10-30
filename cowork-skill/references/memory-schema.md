# Memory schema

Types: `fact`, `project-state`, `decision`, `procedure`, `incident`,
`worked-example`, `hypothesis`, `preference`, `gotcha`.
Statuses: `proposed`, `observed`, `verified`, `stale`, `superseded`, `rejected`.
Confidence: `low`, `medium`, `high`. A hypothesis is a type, not a status.

Checkpoints identify workspace/version/date, goal and constraints, completed verified
work, evidence, failed attempts, open gates and next action. Link sources actually
read. Include applicability and re-verification dates when appropriate.

Read existing titles before revising. Use fresh SHA-256, preserve complementary
lessons and save a complete current snapshot. Omitted/null metadata is preserved;
empty values clear it. Promotion to verified requires fresh evidence. Supersession
applies only to the replaced scope. Read substantive writes back. A timeout may
already have committed; read before retrying. Never store credentials/transcripts.
