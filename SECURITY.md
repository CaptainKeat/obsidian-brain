# Security and local data

Use environment variables or ignored local configuration for credentials.
Never commit tokens, passwords, recovery phrases, browser sessions, personal
documents, logs or generated media. Examples contain no production accounts.

Run local interfaces on loopback. Do not expose them through a public tunnel
or bind them to a public network without adding authentication and reviewing
their file and process access. Credential scanning cannot prove the absence
of every secret or vulnerability. Revoke or rotate any exposed credential.

Report vulnerabilities through this repository's private security reporting
if enabled. Do not put secret values in a public issue or pull request.
