# Changelog

All notable changes to this project will be documented here. Format follows Keep a Changelog; versioning follows SemVer. The packet `schema_version` is versioned separately (see `docs/PACKET_SCHEMA.md`).

## [Unreleased]

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
- Deterministic and statistical benchmark harnesses (`swallo bench run` and `swallo bench verify`).

### Security
- Defense matrix against Zip-Slip, decompression bombs, symlink escapes, path traversal, and JSON nesting limits.
- Mandatory interactive TTY approval for context injection; no approve tools exposed to MCP agents.
- Registered project root enforcement preventing arbitrary directory traversal or rogue MCP workspace configurations.
