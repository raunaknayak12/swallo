# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

- Report privately through GitHub's Private Vulnerability Reporting on this repository (preferred), or email `raunakpython11@gmail.com`.
- Include affected version, reproduction steps, and impact.
- Expect an acknowledgement within 48 hours and a preliminary assessment within 7 days.

## Scope

In scope: the `swallo` package, its CLI, MCP server, importers, redaction, store, and release pipeline.
Out of scope: vulnerabilities in third-party chat apps, IDEs or model providers, and attacks that require an already-compromised local machine.

## What this tool does not guarantee

- Redaction reduces secret exposure but cannot be proven complete.
- Labelling and separating imported content reduces prompt-injection risk but does not eliminate it.
- The tool cannot confirm that a receiving agent read or understood a packet.

See `docs/Security.md` for the full threat model.

## Supported versions

Only the latest minor release receives security fixes during the 0.x series.
