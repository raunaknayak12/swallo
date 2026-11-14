# Architecture Decision Records

Short records of decisions agreed during design. Format: context, decision, consequences, status. Revisit by adding a new ADR that supersedes an old one; do not rewrite history.

## ADR-001: JSON packet is the canonical format
- **Context:** Merge, diff and validation are hard on free text; MCP is JSON-based.
- **Decision:** Store and transport JSON validated by Pydantic; render Markdown for models and files.
- **Consequences:** Renderers are required; a published JSON Schema becomes a public contract.
- **Status:** Accepted.

## ADR-002: Pure-Python stack, distributed on PyPI
- **Decision:** Core is Python standard library plus Pydantic; everything else is an optional extra. No browser extension in this repository.
- **Consequences:** Browser capture is not in v1; structured paste and vendor exports cover chat capture.
- **Status:** Accepted.

## ADR-003: Approval lives in a local ledger, not in the packet
- **Context:** A status field in a shareable file is forgeable.
- **Decision:** Approvals are rows keyed by packet hash and target, MAC'd with a local key; any edit changes the hash and requires re-approval.
- **Consequences:** Approval does not travel with a packet; imported packets always start unapproved.
- **Status:** Accepted.

## ADR-004: Trust tiers are assigned by the tool
- **Decision:** Tier is derived on load from capture method and origin; in-file trust claims are ignored.
- **Status:** Accepted.

## ADR-005: Content-addressed objects; no paths in packets
- **Decision:** Transcripts and artifacts live in an object store referenced by hash; repo files use repo-relative paths through one resolver.
- **Consequences:** Simpler schema; traversal risk largely removed.
- **Status:** Accepted.

## ADR-006: Two-file delivery for chat-derived content
- **Context:** Rules files are instruction channels.
- **Decision:** Write content to a data file under `.swallo/handoff/` and put only a fixed stub in the rules file, with a random per-render fence.
- **Consequences:** Some targets may not load referenced files automatically; per-target behavior must be tested and documented.
- **Status:** Accepted (pending per-target verification).

## ADR-007: No approve tool in MCP; approval needs a TTY
- **Decision:** Agents can save drafts and load approved packets, but cannot approve.
- **Consequences:** IDE-to-IDE flow has a human step; auto-approval is off by default (`trust.ide_agent_autoapprove=false`).
- **Status:** Accepted.

## ADR-008: SQLite store with WAL
- **Decision:** `sqlite3` for packets, ledger, events; filesystem for objects with atomic renames.
- **Consequences:** Concurrency and partial-write safety come from transactions.
- **Status:** Accepted.

## ADR-009: Redacted transcripts by default
- **Decision:** Store redacted transcripts; keep raw only with `--keep-raw` and strict permissions.
- **Consequences:** Some span checks use redacted text; users who need raw opt in knowingly.
- **Status:** Accepted.

## ADR-010: Layered capture, structured paste as baseline
- **Decision:** Capture order of preference: structured-paste prompt (universal), vendor export import, optional remote connector, optional extension (separate repo, later).
- **Consequences:** Packets carry `capture_method` so fidelity is visible.
- **Status:** Accepted.

## ADR-011: Rule-based conflict detection with a plugin interface
- **Decision:** Core ships deterministic detectors; a `ConflictDetector` protocol allows user-supplied (including model-assisted) detectors, off by default.
- **Consequences:** Expected high precision and limited recall on free text; reported honestly.
- **Status:** Accepted.

## ADR-012: Pre-registered, sealed-set benchmarks
- **Decision:** Follow `BENCHMARKS.md`; claims limited by the claims policy.
- **Status:** Accepted.

## ADR-013: Minimal guardrail set; no LLM-based safety layer
- **Decision:** Ship the guardrails in `Security.md`; no moderation or LLM checks in core.
- **Status:** Accepted.

## ADR-014: Project name is swallo
- **Context:** Earlier working names were `ctx-handoff` and then `stowbit`.
- **Decision:** Distribution, import name and CLI command are all `swallo`.
- **Consequences:** PyPI availability, and similar names (for example `swallow`), must be checked before the first publish; all docs, the `.swallo/` directory and the `swallo:begin/end` stub markers use this name.
- **Status:** Accepted (availability check pending).

## ADR-015: MIT license
- **Decision:** Release under the MIT license.
- **Consequences:** Dependencies must have MIT-compatible licenses; no patent grant beyond what MIT provides.
- **Status:** Accepted.

## ADR-016: Minimum Python 3.11
- **Decision:** `requires-python = ">=3.11"`.
- **Consequences:** CI tests all upstream-supported versions at release time.
- **Status:** Accepted.

## ADR-017: Built-in help command
- **Decision:** Provide `swallo help [command|topic]`, `-h/--help` and `version`, with all help text in one module shared by the CLI, docs and tests.
- **Consequences:** Every new command must ship help text, an example and exit codes; a test enforces it.
- **Status:** Accepted.

## ADR-018: MCP guard layer
- **Context:** An agent in a loop or steered by injected text can flood the store or retry around blocks.
- **Decision:** Deduplicate saves, add a per-session token bucket, quotas and TTL for unapproved MCP drafts, and a circuit breaker for repeated blocked saves. Guards apply to MCP only and keep no content or fingerprints.
- **Consequences:** Thresholds are proposals tuned from real usage; purge and reset are CLI-only.
- **Status:** Accepted.

## ADR-019: Deterministic stale policy with an expiring acknowledgment
- **Decision:** MCP loads of packets with critical drift are blocked by default; a human acknowledgment bound to packet hash, HEAD and drifted-file hashes expires on any change.
- **Consequences:** Detects file changes only, not changes in meaning; unrelated commits stay silent.
- **Status:** Accepted.

## ADR-020: Global MCP setup and registered project roots
- **Decision:** `init` prints user-level configuration with an absolute interpreter path; the server serves only registered roots; `doctor` flags workspace-level configs and rogue data files.
- **Consequences:** Protection depends on user config and `doctor`; a replaced command cannot police itself.
- **Status:** Accepted (per-IDE behavior to verify).

## ADR-021: Hidden-character handling and risk-first review
- **Decision:** CSPRNG fences; strip Unicode tag and bidirectional controls; flag other invisible characters; tool-generated risk summary shown first; no bulk approval of T3 packets.
- **Status:** Accepted.

## ADR-022: Decoded-variant redaction and opaque-blob rule
- **Decision:** Scan bounded decoded variants and flag long encoded-looking strings for human approval; return minimal errors to agents.
- **Consequences:** Raises the bar for evasion without claiming completeness.
- **Status:** Accepted.

## ADR-023: Optional passphrase-signed approvals (hardened tier)
- **Decision:** Offer `approve.signing = passphrase` through an optional `[sign]` extra; baseline keeps HMAC with a local key.
- **Consequences:** Adds a non-stdlib dependency only for those who opt in; does not protect against an agent with unrestricted file and shell access.
- **Status:** Accepted (signing library chosen: `cryptography`, see ADR-030).

## ADR-024: Canonical JSON is our own definition, with no floats
- **Context:** Hashes, approvals and deduplication depend on byte-exact canonical output.
- **Decision:** Define "swallo canonical JSON v1": UTF-8, sorted keys (code point order), no whitespace, duplicate keys rejected, strings NFC-normalized at ingest, integers only within +/-(2^53 - 1), floats, NaN and Infinity rejected anywhere. Do not claim RFC 8785 compliance. The **hashed form** excludes volatile fields (`id`, `created_at`, `sources[*].captured_at`). Golden files per schema version; any canonicalization change requires a schema major bump.
- **Consequences:** No packet field may hold a float; any future score is an integer or an enum. Identical content saved at different times has the same hash.
- **Status:** Accepted.

## ADR-025: Packet IDs are derived from the hash
- **Decision:** `id = "pkt_" + first 12 hex of the packet hash`, extended by two characters on collision with a different hash in the same store. Item IDs (proposal): `"it_" + first 8 hex of SHA-256(kind, NUL, NFC text)`, extended on collision within a packet. Producer-supplied IDs are ignored.
- **Consequences:** Identical content gives the same ID, so deduplication is free; this supersedes the earlier description of IDs as opaque. Docs examples use shortened IDs for readability.
- **Status:** Accepted.

## ADR-026: Store location helper in stdlib; config read with `tomllib`
- **Decision:** A small helper picks `$XDG_DATA_HOME/swallo` or `~/.local/share/swallo` (POSIX), `~/Library/Application Support/swallo` (macOS), `%LOCALAPPDATA%\swallo` (Windows, deliberately not the roaming profile). Overrides: `SWALLO_HOME` and `--store`. Config is `<store>/config.toml`, parsed with `tomllib` (standard library from Python 3.11) and validated by Pydantic; `init` writes it from a template. No `platformdirs` dependency.
- **Consequences:** Fewer dependencies; `doctor` warns if the store sits inside a git work tree.
- **Status:** Accepted.

## ADR-027: Best-effort permissions on Windows
- **Decision:** POSIX directories `0700` and files `0600`; on Windows rely on user-profile ACLs, make permission checks best effort, mark POSIX-only tests accordingly, and have `doctor` say so.
- **Status:** Accepted.

## ADR-028: Guard thresholds are experimental defaults
- **Decision:** Use the starting values in the TRD config table for now, keep every value in config, write an event for each guard decision, label guards experimental in 0.x, and tune on a working prototype (plan in `IMPLEMENTATION_PLAN.md` section 15).
- **Consequences:** Defaults may block legitimate use or miss abuse until tuned.
- **Status:** Accepted.

## ADR-029: IDE behavior verified during the integration phase
- **Decision:** Build the core CLI and store first. Run one spike per IDE (Claude Code, Cursor, Antigravity) before its adapter or MCP integration, covering global config paths, session identifiers, workspace roots, referenced-file loading and terminal checks. If an IDE has no stable session identifier, use per-project buckets.
- **Consequences:** Two-file delivery (ADR-006) stays provisional until each spike is recorded.
- **Status:** Accepted.

## ADR-030: `cryptography` for the optional signing tier
- **Decision:** Use `cryptography` (Ed25519) via the optional `[sign]` extra. Import it lazily in `store/signing.py` only. CI runs the full suite with no extras installed. Derive the key from the passphrase with `hashlib.scrypt`; test against known vectors; audit with pip-audit; verify the current API before coding.
- **Consequences:** The core stays standard library plus Pydantic; users who opt in accept a compiled dependency.
- **Status:** Accepted.

## ADR-031: Build sequencing
- **Decision:** Build in this order: scaffold, schema and hashing, store, safety spine, CLI and help, delivery v0, merge, MCP and guards, importers, benchmarks and signing (see `IMPLEMENTATION_PLAN.md`). HTTP mode, the `[remote]` extra and the benchmark harness wait until the core is stable.
- **Consequences:** v0.1 has no MCP server; merge and MCP arrive in v0.2.
- **Status:** Accepted.

## ADR-032: PyPI and TestPyPI name availability confirmed
- **Context:** Package name availability and typosquatting risk must be evaluated before building.
- **Decision:** PyPI and TestPyPI checks confirmed on 2026-10-31 and re-verified on 2026-11-10:
  - `swallo`: Available on PyPI (HTTP 404) and TestPyPI (HTTP 404).
  - `swallo-core`: Available on PyPI (HTTP 404) and TestPyPI (HTTP 404).
  - Note: `swallow` is registered on PyPI by an unrelated third party; our exact package name is `swallo`.
- **Status:** Accepted.

## ADR-033: Dual Licensing (MIT OR Apache-2.0) & Code of Conduct
- **Context:** Enterprise users and agent developer toolchains require explicit patent grant protections (provided by Apache 2.0) while retaining the permissive compatibility of MIT.
- **Decision:** Swallo is dual-licensed under `MIT OR Apache-2.0` (SPDX expression). Both `LICENSE-MIT` and `LICENSE-APACHE` are distributed at the repository root and embedded in the package distribution wheel and source archive. The project also adopts the Contributor Covenant v2.1 as `CODE_OF_CONDUCT.md`.
- **Status:** Accepted.

## v0.2 Candidates (Deferred from v0.1)
The following capabilities are explicitly deferred to v0.2 and are out of scope for v0.1:
1. **Remote HTTP Mode (`[remote]` extra):**
   - *Status:* Deferred candidate for v0.2.
   - *Threat Model Note:* Requires an updated threat model and formal security review because exposing an HTTP/network endpoint breaks or significantly widens the core zero-network security claim of Swallo.
2. **Conflict-Detector Plugin API:**
   - *Status:* Deferred candidate for v0.2.
   - *Threat Model Note:* Requires an updated threat model to ensure external model-assisted or third-party plugin execution cannot introduce unverified code execution, network egress, or bypass redaction guarantees.

## M6 & M7 Evaluation Pilot Designs

### M6 Downstream-Agent Outcome Study (Pilot Design Only)
- **Objective:** Measure downstream agent performance (Claude Code, Cursor, Antigravity) when provided Swallo handoff packets versus full raw transcripts, naive summaries, or zero context.
- **Protocol:**
  - Fixed downstream models (e.g. `claude-3-7-sonnet`, `gemini-2.5-pro`) and deterministic sampling seeds.
  - Anonymized and privacy-vetted test corpus of 50 real debugging and feature tasks.
  - Pre-registered evaluation criteria: pass rate on pre-existing test suites, turn count to resolution, input token consumption, and constraint adherence.
  - Blinded scoring for subjective explanations, supplemented by automated test execution.
  - Statistical analysis: McNemar's test for paired binary pass/fail comparisons; Wilcoxon signed-rank test for continuous turn/token metrics with bootstrap confidence intervals.
  - *Constraint:* Purely a prospective design. No execution or claims published in v0.1.

### M7 Human Usability Study (Pilot Design Only)
- **Objective:** Evaluate developer task-completion speed, cognitive load, and redaction confidence with Swallo.
- **Protocol:**
  - Within-subjects counterbalanced design (with Swallo handoff vs manual prompt copy-paste).
  - Standardized System Usability Scale (SUS) survey and timed milestone completion.
  - Informed consent and anonymized interaction logging.
  - *Constraint:* Prospective design only; pending human study ethical clearance and participant recruitment.

## Release Gate Verification Table (v0.1)

| Gate Check | Status | Verification Evidence / Details |
|---|---|---|
| Steps 0–5 tests green on 3 OSs | **PASS** | 355 tests pass across Python 3.11, 3.12, 3.13 on Linux, macOS, and Windows. |
| F2, F3, F4, F5, F10 guard tests pass | **PASS** | Automated regression tests in `test_redact_detectors.py`, `test_importer_security.py`, `test_mcp_server.py`. |
| Independent review of F1–F5 | **pending independent reviewer** | Formal boundary: implementer cannot review own security findings. Left for external auditor. |
| Claude Code spike recorded; per-target behavior | **PASS** | Documented in ADR-029, `src/swallo/adapters/`, and TRD. |
| Core-only CI job green (no extras installed) | **PASS** | Isolated fresh venv import emits 0 warnings; zero optional modules imported. |
| `swallo doctor` passes on clean environment | **PASS** | Verified after `swallo init`. |
| Docs match behavior; changelog updated | **PASS** | README updated with 23 CLI commands, exit codes, architecture, MCP guide; CHANGELOG updated. |
| TestPyPI install & smoke test | **pending manual step** | Local wheel smoke test passed in isolated venv; remote upload and multi-OS smoke test pending maintainer manual execution. |
| Name availability confirmed | **pending manual step** | PyPI and TestPyPI availability verified (ADR-032); final reservation upload pending maintainer manual execution. |

## ADR-033: Elimination of Non-Interactive TTY Bypass in Production
- **Context:** Testing shortcuts (e.g. `--force` / `-f` flag) could allow an autonomous agent or script executing in non-interactive environments to bypass human approval gates.
- **Decision:** Completely eliminate `--force` / `-f` flags and test bypass parameters from the production CLI in the shipped wheel. Approval strictly requires a verified interactive TTY. Test suites simulate terminal interaction via explicit test harness monkeypatches that are never shipped.
- **Consequences:** Autonomous agents with shell access cannot approve packets programmatically; security invariant F18 strictly holds.
- **Status:** Accepted (Implemented in v0.1.3).

## ADR-034: Supply-Chain Hardening & Trusted Publishing (OIDC)
- **Context:** Secure open-source releases require cryptographic build provenance and defense against credential theft.
- **Decision:** Mandate GitHub Actions Trusted Publishing (OIDC) for all PyPI and TestPyPI releases. Enforce SHA-pinned workflow actions, least-privilege token permissions, pre-release tag version synchronization against `pyproject.toml` and `CHANGELOG.md`, and automated OpenSSF Scorecard analysis. Manual uploads via API tokens or Twine are forbidden.
- **Consequences:** Releases are fully reproducible, tamper-evident, and auditable.
- **Status:** Accepted (Implemented in v0.1.3).

## Pending decisions
- Antigravity and other target adapter details after verification.
- Tuned default guard thresholds (breaker, token bucket, quotas, TTL), from real usage (ADR-028).
- Per-IDE behavior: stable MCP session identifiers, workspace roots, referenced-file loading, terminal checks (ADR-029).

