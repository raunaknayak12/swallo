# Mustel MCP — IDE Verification Notes

**Date:** 2026-10-31
**Reviewer:** raunaknayak12 (via Mustel MCP v0.6.4)

## What is Mustel?

Mustel is a static-analysis MCP server that inspects every `git commit` in the
workspace. It automatically surfaces:

| Category | Scope |
|---|---|
| **Security** | SQL injection, secrets in code, unsafe shell invocations |
| **Package Vulns** | Known CVEs in transitive dependencies (via pip-audit) |
| **Errors** | Type errors, import issues, unreachable code |
| **Warnings** | Style, complexity, dead code |

## Setup

Mustel is configured as an MCP server in the workspace's `.agents/` directory.
It hooks into `git commit` via a pre-commit integration and posts its report
JSON alongside the commit output.

## Findings Summary (Commits 1–9)

### S001 / S002 — PRAGMA user_version interpolation (False Positive)

**File:** `src/swallo/store/db.py`
**Flagged lines:**
- `conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")`
- `cur.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")`

**Verdict: False positive.** Both interpolated values come from:
1. `busy_timeout_ms` — a typed `int` function parameter with default `5000`.
2. `SCHEMA_VERSION` — a module-level `int` constant (`= 1`).

Neither value is user-controlled. To further harden, explicit `int()` casts
were added so that even if a future refactor accidentally passes a string, it
would raise `ValueError` rather than allowing injection.

### P001–P057 — Package Vulnerabilities

These are CVEs in **transitive dependencies** of the development toolchain
(e.g., pip, setuptools, hypothesis, pluggy). They do **not** affect `swallo`
runtime code. Mitigation:

- `pip-audit` is run in CI (`pip-audit.yml`) to catch new vulns on every PR.
- Dev dependencies are pinned via `pyproject.toml` optional groups and
  periodically updated.

### E001–E009 — Errors

Static analysis errors reported during early commits when modules were being
built incrementally (e.g., importing `swallo.errors` before `errors.py`
existed). All resolved by commit 8.

## Verification Checklist

- [x] Mustel MCP server connected and responding
- [x] Pre-commit hook fires on every `git commit`
- [x] Security findings (S001, S002) triaged as false positives with hardening
- [x] Package vulnerabilities tracked; CI pip-audit covers ongoing monitoring
- [x] All static-analysis errors resolved in final commit state
- [x] 48/48 tests passing with no regressions
