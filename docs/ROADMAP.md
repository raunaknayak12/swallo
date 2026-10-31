# Roadmap

**Status:** Draft v0.1. Dates are intentionally absent; milestones are ordered by dependency and each has exit criteria.

| Milestone | Deliverables | Exit criteria |
|---|---|---|
| **M0 Foundations** | Repo, `pyproject.toml`, CI (lint, types, tests, audit), license, CODEOWNERS, name and PyPI availability confirmed, `SECURITY.md` live | CI green on Linux/macOS/Windows; TestPyPI dry-run publishes |
| **M1 Core contract** | Pydantic models, canonical JSON and hashing, JSON Schema export, schema fixtures, SQLite store, object store, limits | Round-trip and determinism property tests pass; golden files committed |
| **M2 Safety spine** | Redaction engine (patterns, entropy, deny-list), keyed placeholders, ledger, hash-chained event log, path resolver, sanitizer with hidden-character handling, decoded-variant scanning, opaque-blob rule | F2, F3, F4, F10 tests pass; redaction baseline measured on a first corpus slice |
| **M3 CLI, safety spine and delivery v0 (v0.1)** | `init`, `help`, `version`, `doctor`, `prompt`, `save`, `show`, `approve`, `list`, `status`, `log`, `send`, `load`; Claude Code and briefing adapters; two-file delivery | End-to-end chat-to-IDE and chat-to-chat flows work offline; Claude Code pickup behavior verified in a spike; independent review of F1-F5 done |
| **M4 Merge, MCP and guards (v0.2)** | Merge, dedupe, conflicts, resolve in all flows; stdio MCP server with guards (circuit breaker, rate limit, quotas and TTL, stale policy, root registry); staleness; global-only `init` and `doctor` MCP checks; Cursor adapter after its IDE spike | Conflict fixtures with hard negatives pass; MCP integration tests and the 500-call loop pass; IDE behaviors verified and recorded; staleness tests pass |
| **M5 Importers and evidence (v0.3)** | Importers (ChatGPT first) with archive-limit tests; Antigravity and AGENTS.md adapters after their spikes; Corpus with consent and sealed split, annotation, Phase 1 and 2 harnesses, `swallo bench run/verify`, competitor protocol, cost pilot | Pre-registration committed before sealed-set runs; first published Phase 1 results with environment manifest |
| **M6 Outcome study** | Phase 3 downstream comparison, at least two downstream models, paired statistics | Results published with confidence intervals, including negative results |
| **M7 Extensions** | Gemini/Claude import, optional remote HTTP mode, optional passphrase-signed approvals (`[sign]`), conflict-detector plugins, human study | Findings F12 (if built) tested; study protocol approved |

The step-by-step engineering sequence (Steps 0-8, with interfaces, tests and exit criteria) is in `IMPLEMENTATION_PLAN.md`. Mapping: Step 0 to M0; Steps 1-2 to M1; Step 3 to M2; Steps 4-5 to M3; Steps 6-7 to M4; Step 8 and the benchmark harness to M5 onward.

## Initial backlog (first issues to open)

1. Confirm `swallo` is available on PyPI; add the MIT `LICENSE`; set `requires-python = ">=3.11"`.
2. Implement canonical JSON and hash with golden tests.
3. Pydantic models and generated JSON Schema.
4. SQLite store with WAL and immediate transactions; parallel-saver test.
5. Redaction engine with detector interface and fail-closed mode.
6. Keyed placeholder scheme and leak-scan test harness.
7. Approval ledger and TTY-only approve command.
8. Hash-chained log and `--verify`.
9. Shared path resolver with fuzz tests.
10. Fence and two-file delivery for the Claude Code adapter; test pickup behavior.
11. Cursor adapter and chat briefing renderer.
12. MCP server tools and test client.
13. Structured-paste prompt and its validation errors.
14. Token budget with `critical` handling.
15. Merge pipeline and conflict fixtures.
16. Staleness checker with temp-repo tests.
17. ChatGPT importer with archive-limit tests.
18. Benchmark manifest and results schema.
18a. `swallo help` and `swallo version`, with per-command help text and topics (`flows`, `exit-codes`, `config`, `security`).
19. Corpus consent and redaction-audit process.
20. Pre-registration template filled and committed.
21. Decoded-variant scanner and opaque-blob rule, with obfuscated-secret fixtures.
22. MCP circuit breaker with SQLite state and `swallo breaker`.
23. Token bucket, dedupe, quotas, TTL and `swallo drafts`.
24. Critical-drift rule, `stale_context_blocked`, and the expiring `--ack-stale` acknowledgment.
25. Project root registry, global-only `init` snippet, and `doctor` checks for workspace configs and rogue data files.
26. Hidden-character handling, tool-generated risk summary, and `--accept-untrusted`.
27. Optional passphrase-signed approvals and re-init guard.

## Principles for changing the roadmap

- Security spine (M2) comes before delivery adapters (M3).
- No benchmark claim ships before its pre-registration is committed.
- Optional modules (remote mode, extension) never block core milestones.
