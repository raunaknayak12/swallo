# Changelog

All notable changes to this project will be documented here. Format follows Keep a Changelog; versioning follows SemVer. The packet `schema_version` is versioned separately (see `docs/PACKET_SCHEMA.md`).

## [Unreleased]

- Security update: findings F16-F21 and mitigations (decoded-variant redaction with circuit breaker, hidden-character handling and risk-first review, deterministic stale policy with expiring acknowledgment, draft dedupe/rate limits/quotas/TTL, global-only MCP setup with registered roots, optional passphrase-signed approvals); new commands `drafts` and `breaker`; new errors `session_paused`, `rate_limited`, `stale_context_blocked`, `unregistered_project`; ADR-018 to ADR-023.
- Project renamed to swallo (previously stowbit, and before that ctx-handoff); package, command, `.swallo/` directory and stub markers updated everywhere.
- Settled implementation decisions recorded as ADR-024 to ADR-031 (canonical JSON, derived IDs, store location and config, Windows permissions, experimental guard defaults, IDE verification, `cryptography` signing extra, build sequencing); schema doc, TRD, PRD, roadmap and security docs updated.
- Added `docs/IMPLEMENTATION_PLAN.md`.
- Project named swallo; MIT license; minimum Python 3.11; `help` and `version` commands specified (`docs/COMMANDS.md`).
- Documentation pack drafted (PRD, TRD, Security, Paper, schema, CLI/MCP spec, benchmarks, roadmap, packaging).
