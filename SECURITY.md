# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x (latest) | ✅ Active |
| < 0.1.0 | ❌ No longer supported |

Security fixes are released as patch updates on the latest `0.1.x` series. Older versions do not receive backported security patches.

## Reporting a Vulnerability

**Please do not open a public GitHub Issue for security problems.**

Use [GitHub private vulnerability reporting](https://github.com/raunaknayak12/swallo/security/advisories/new) (preferred): click "Report a vulnerability" to open a draft advisory visible only to maintainers. Alternatively, email `raunakpython11@gmail.com` with subject `[SECURITY] swallo <brief description>`.

**Include in your report:**
- Affected version(s) (`swallo --version`)
- Steps to reproduce
- Potential impact
- Suggested fix (optional)

## Response Timeline

| Stage | Target |
|-------|--------|
| Initial acknowledgement | Within 72 hours |
| Triage and severity assessment | Within 7 days |
| Fix and patch release | Within 30 days (critical/high); 90 days (medium/low) |
| Public disclosure | After fix is released or 90 days, whichever comes first |

## Scope

**In-scope:**
- `swallo` package code under `src/swallo/` on the latest published PyPI release
- Security invariants: TTY approval gate, MCP approve-tool absence, zero-network core, fences, redaction, ledger HMAC chain
- Credential or secret leakage through the CLI, store, or MCP server

**Out-of-scope:**
- Vulnerabilities in `swallo`'s optional dependencies (`mcp`, `cryptography`, `tiktoken`, `pydantic`) — report those upstream
- Issues in development-only dependencies (`pytest`, `ruff`, `mypy`, etc.)
- Attacks requiring physical access to the machine running `swallo`
- Social engineering of the user who operates `swallo approve`

## Security Architecture Notes

- **Zero network egress**: The core runtime (`pip install swallo` without extras) makes no outbound network calls. Enforced by an AST-level test (`tests/test_zero_network.py`).
- **TTY-required approval**: `swallo approve` requires an interactive terminal (TTY). Cannot be bypassed via CLI flags, environment variables, or the MCP server. No `--force` flag exists in production.
- **No approve tool in MCP**: Per ADR-007, the MCP server exposes zero approval tools. Human review is strictly CLI-only.
- **Redaction is best-effort**: The redaction engine catches many common secret patterns with decoded-variant scanning, but cannot guarantee detection of all custom or obfuscated secrets. Users must review packets before approval.
- **v0.1, not independently audited**: This is an early release. It has not undergone a formal third-party security audit. CodeQL, Bandit, and pip-audit run on every CI build (see [CI badges](https://github.com/raunaknayak12/swallo#readme)).
