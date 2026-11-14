# Changelog

All notable changes to this project will be documented here. Format follows Keep a Changelog; versioning follows SemVer. The packet `schema_version` is versioned separately (see `docs/PACKET_SCHEMA.md`).

## [0.1.3] - 2026-11-13

### Security
- **terminal**: Enforce ANSI escape and terminal control character sanitization on packet metadata, goals, project names, and warnings rendered by `swallo show`, `swallo status`, and `swallo list` to defend against terminal injection attacks.
- **approve**: Removed `--force` / `-f` testing bypass flag from `swallo approve` CLI in production code, guaranteeing mandatory human approval on interactive TTYs without non-interactive bypass vectors.
- **config**: Disallow `ide_agent_autoapprove = true` configuration to prevent autonomous agents from subverting human approval gates.

### Fixed
- **status / list**: Decode SQLite `body` column BLOB bytes (`bytes` or `memoryview`) into UTF-8 text prior to canonical JSON parsing. Gracefully report corrupted rows as `<corrupt>` with warning output rather than crashing.
- **prompt**: Make Pydantic `Item` model the authoritative source of truth. Derive valid kinds (`decision`, `constraint`, `question`, `artifact_ref`) dynamically in prompt output; sample JSON now includes required `created_at` and `sources` fields.
- **targets**: Normalize target names uniformly across `approve`, `send`, `show`, and `ledger`. Supported targets are determined dynamically from adapter registry (`claude-code`, `antigravity`, `chat`).
- **approve**: Added helpful error messages for unknown delivery targets and set default target to `claude-code`.
- **prompt CLI**: Added helpful error message when `-t` is passed as an ingestion title rather than target adapter name.

### Added
- **config**: Added support for `SWALLO_STORAGE_DIR` as an environment variable alias for `SWALLO_HOME`, with precedence warning if both are set and differ, and hints for unrecognized `SWALLO_*` variables.
- **send**: Added `--format markdown` flag for compatibility with documentation.
- **mcp**: Added `verify_context` tool for read-only integrity, event-chain HMAC verification, and ledger status inspection.
- **mcp**: Added `get_context` tool alias for `load_context` matching documented MCP server interfaces.
- **test**: Comprehensive end-to-end regression suite (`tests/e2e/test_full_flow.py`) validating the entire lifecycle.
- **security**: Zero-network AST scan test (`tests/test_zero_network.py`) enforcing complete absence of network client imports.
- **docs**: Auto-generating CLI reference script (`scripts/gen_cli_docs.py`).

### Compatibility
- Existing stores created by `swallo 0.1.2` remain fully compatible.
- Historical ledger approvals with legacy target strings (`claude_code`) are automatically recognized and verified without database mutations or re-MACing.

## [0.1.2] - 2026-11-12

### Fixed
- Enriched PyPI discovery metadata, keywords, and release documentation.

## [0.1.1] - 2026-11-12

### Fixed
- Added author contact email and updated badges.

## [0.1.0] - 2026-11-10

### Added
- Core context handoff CLI with 23 commands: `init`, `doctor`, `prompt`, `save`, `import`, `merge`, `resolve`, `show`, `edit`, `approve`, `send`, `load`, `diff`, `list`, `status`, `log`, `staleness`, `drafts`, `breaker`, `bench`, `mcp`, `help`, `version`.
- Zero-network runtime with content-addressed packet store in SQLite WAL mode.
- Swallo Canonical JSON v1 serialization and SHA-256 integrity hashing without floating-point numbers.
- Secret and PII redaction engine with decoded-variant scanning (base64, hex, URL, rot13, reverse, zero-width) and decode-bomb caps.
- Trojan Source sanitizer neutralizing bidirectional override and Unicode tag controls (CVE-2021-42574).
- Anti-tamper verification across event log hash chains and MAC-signed approval ledgers.
- Model Context Protocol (MCP) server with draft quotas, per-session token bucket, and circuit breakers.
- Adapters for Claude Code, Cursor, and Antigravity IDEs.
- Optional passphrase-derived Ed25519 digital signatures (`[sign]` extra via cryptography).
- Deterministic and statistical benchmark harnesses (`swallo bench run` and `swallo bench verify`) with 164-sample anti-overfitting corpus and 20-round realistic-transcript throughput suite.
- Dual licensing under MIT and Apache-2.0 (`LICENSE-MIT` and `LICENSE-APACHE`).
- Contributor Covenant Code of Conduct v2.1 (`CODE_OF_CONDUCT.md`).

### Security
- Defense matrix against Zip-Slip, decompression bombs, symlink escapes, path traversal, and JSON nesting limits.
- Mandatory interactive TTY approval for context injection; no approve tools exposed to MCP agents.
- Registered project root enforcement preventing arbitrary directory traversal or rogue MCP workspace configurations.
