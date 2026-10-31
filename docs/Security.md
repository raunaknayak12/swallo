# Security Design and Threat Model

**Status:** Draft v0.2 | **Date:** 2026-10-25 | Live tracking: `security/FINDINGS_REGISTER.md`

## 0. How to read this document

- The findings below come from reasoning about the design, not from observing code. No code exists yet. Each finding is a **hypothesis** until its test is run.
- Severity ratings are estimates and change only when test results justify it.
- The list was AI-assisted and is not complete. A human security review and external scanners are required checks on it.
- Mitigations reduce specific risks. Nothing here makes the tool "secure" in an absolute sense.

## 1. Security goals

1. Secrets and PII in captured conversations do not persist in the store, packets, logs or errors (to a measured, published recall).
2. Imported or chat-derived text is never treated as instructions by the tool and is delivered to agents as data.
3. A human approves what leaves the machine; that approval cannot be forged by a packet file or an agent.
4. Malformed or hostile files cannot crash the tool, escape the store or project root, or exhaust resources.
5. Users can see what happened (hash-chained event log) and detect tampering.
6. Runaway or manipulated agents cannot flood the store, evade blocks by retrying, or load stale context without a human decision.

### Non-goals and assumptions
- Does not fully defend against malware, or a compromised agent with unrestricted file and shell access, running with the user's privileges. The optional signed-approval tier raises the bar; real containment comes from the IDE's sandbox and permission prompts (see F21).
- Does not guarantee a receiving model ignores injected text.
- Does not guarantee redaction completeness.
- Does not control what third-party chat apps or IDEs do with text once delivered.

## 2. Assets, actors, boundaries

**Assets:** secrets/PII in transcripts; the packet store; approval ledger and local key; integrity of the briefing a next agent receives; the user's repo; the benchmark corpus.

**Actors:** the user; the user's IDE and chat agents (semi-trusted, can be influenced by hostile content); authors of pasted or imported content (untrusted); other local processes and browser pages; contributors and dependency maintainers; optional remote clients.

**Trust boundaries (untrusted data crosses each):**

| # | Boundary | Main risks |
|---|---|---|
| B1 | Pasted/chat text into capture | Injection payloads, secrets |
| B2 | Imported archives and shared packets into parsers | Zip-slip, bombs, forged metadata, path fields |
| B3 | Local clients into any HTTP listener | DNS rebinding, CSRF, missing auth |
| B4 | Packet content into the receiving LLM agent | Prompt injection, instruction hijack |
| B5 | Internet into the optional remote endpoint | Authz failures, IDOR, token abuse |
| B6 | Dependencies and contributors into releases | Supply-chain compromise |
| B7 | IDE and workspace configuration into the MCP launch path | Poisoned workspace MCP config, rogue data files, cross-project loads |

## 3. Security requirements

| ID | Requirement |
|---|---|
| SR-01 | Redaction runs before any write; fail closed by default |
| SR-02 | Approval is recorded locally, bound to packet hash and target, outside the packet |
| SR-03 | Trust is assigned by the tool on load; in-file trust and status are ignored |
| SR-04 | Packets reference objects by hash; repo paths pass one shared resolver |
| SR-05 | Chat-derived content is delivered as a separate data file with a fixed trusted stub |
| SR-06 | No MCP tool can approve; approval requires a TTY |
| SR-07 | All printed untrusted text is sanitized of control and escape sequences |
| SR-08 | Importers enforce size, entry, ratio and depth limits and never use member names as paths |
| SR-09 | Stdio MCP by default; any HTTP mode binds loopback, requires a token and checks Host/Origin |
| SR-10 | Store files use restrictive permissions; the store lives outside the repo |
| SR-11 | Logs and errors never contain secret or transcript text |
| SR-12 | Event log is hash-chained and verifiable |
| SR-13 | Dependencies are minimal, pinned with hashes and audited in CI |
| SR-14 | Critical items are never silently trimmed |
| SR-15 | Merge never auto-supersedes; conflicts require user action |
| SR-16 | Redaction scans bounded decoded variants and flags opaque blobs; errors returned to agents carry a code and count only |
| SR-17 | MCP saves are guarded by a circuit breaker that counts blocked attempts and stores no content or fingerprints |
| SR-18 | Fences use a CSPRNG; Unicode tag and bidirectional control characters are stripped; other invisible format characters are flagged |
| SR-19 | MCP loads of stale context are blocked by default under a deterministic drift rule; acknowledgments are bound to packet hash, HEAD and drifted-file hashes and expire on change |
| SR-20 | MCP saves are deduplicated, rate-limited per session and quota-bound; unapproved MCP drafts expire |
| SR-21 | MCP setup is global with absolute interpreter paths; only registered project roots are served; `doctor` detects workspace-level configs and rogue data files |
| SR-22 | Approval and store re-initialization require a terminal (best effort); an optional tier signs approvals with a passphrase-derived key |

## 4. Findings and mitigations

Severity is an estimate. "Verify by" names the test that confirms or refutes the finding.

### F1. Untrusted text reaches instruction channels (High)
- **Evidence (design):** rules files are instruction channels for agents; the design renders chat-derived text into them; transcripts often contain pasted web pages and documents.
- **Weakness:** a label inside an instruction file is still part of that file.
- **Mitigation:** two-file delivery with a fixed stub; random per-render fence delimiter, regenerated until absent from content; structured fields with length caps; review highlights command-like text; trust tiers decide delivery.
- **Residual risk:** a model may still follow injected text; targets may not load referenced files automatically, which trades some reliability for safety.
- **Verify by:** payload fixtures and delimiter-breakout fuzzing; sandboxed agent tests with no real secrets (model-dependent result).

### F2. Approval state is forgeable (High)
- **Evidence:** a status field inside a shareable packet could claim approval; edits after approval could still deliver.
- **Mitigation:** approval ledger keyed by packet hash and target with a local-key MAC; imported packets start unapproved; any edit changes the hash and forces re-approval.
- **Residual risk:** local malware with access to the key.
- **Verify by:** import a packet claiming approval; edit after approval and attempt delivery.

### F3. Trust metadata is in-band (High)
- **Evidence:** markers such as `untrusted_content` or `provenance` originate from the file.
- **Mitigation:** the tool derives trust tier on load; file-supplied trust and status are ignored.
- **Verify by:** import a packet declaring itself trusted; confirm it is treated as T3.

### F4. Path fields enable traversal and file disclosure (High)
- **Evidence:** earlier schema drafts used path fields for transcripts and artifacts.
- **Mitigation:** content-addressed objects referenced by hash; repo files by repo-relative path through one resolver that rejects absolute paths, `..` and symlink escapes.
- **Verify by:** property tests and fuzzing on traversal, symlinks and Windows-style paths.

### F5. Redaction misses (High)
- **Evidence:** pattern-based redaction cannot catch novel secrets, prose passwords or all PII.
- **Mitigation:** layered detectors (patterns, entropy, optional gitleaks/trufflehog/Presidio), user deny-list, redaction preview at review, redaction applied before every write including logs and errors, keyed placeholders.
- **Residual risk:** unknown secret formats. Publish measured recall; never claim completeness.
- **Verify by:** run external scanners over store, log, temp files and errors on the labelled corpus (`BENCHMARKS.md`).

### F6. Stored raw transcripts; accidental commits (Medium)
- **Evidence:** a raw copy would be a secrets honeypot; rules and data files written into a project can be committed to public repositories.
- **Mitigation:** redacted transcripts by default, raw only with `--keep-raw`; restrictive permissions; store outside the repo; offer `.gitignore` entry; warn on staged swallo files; optional pre-commit check.
- **Verify by:** full flow in a test repo, scan and permission checks.

### F7. Local server exposure (Medium)
- **Evidence:** any HTTP mode is reachable by browser pages unless Host/Origin are checked and a token is required.
- **Mitigation:** stdio default; loopback bind; per-install bearer token; Host/Origin allow-list; explicit flag for non-loopback.
- **Verify by:** spoofed Host/Origin requests; page-initiated fetch to localhost; bind-address check.

### F8. Import parsers (Medium)
- **Evidence:** vendor archives and shared packets are untrusted files.
- **Mitigation:** stream parsing, hard limits, no member-name paths, optional subprocess isolation.
- **Verify by:** zip-slip, decompression bomb, huge JSON and deep nesting fixtures.

### F9. Merge poisoning (Medium)
- **Evidence:** a session can carry a "decision" that overrides a real constraint; paste provenance is user-asserted.
- **Mitigation:** no auto-supersede; override-language flagged; source and `capture_method` shown per merged item; paste content labelled user-asserted.
- **Residual risk:** limited recall of rule-based conflict detection on free text.
- **Verify by:** adversarial merge fixtures; recall measured on the real corpus.

### F10. Output handling and log integrity (Medium)
- **Evidence:** untrusted text is printed by `swallo show` and `swallo log`; local logs can be edited.
- **Mitigation:** control and escape-sequence stripping; data-only formatting with no eval/format on untrusted strings; autoescaping if templates are used; hash-chained log with `swallo log --verify`.
- **Residual risk:** tamper-evident, not tamper-proof.
- **Verify by:** escape-sequence and template-payload fixtures; edit a log row and verify detection.

### F11. Supply chain (Medium)
- **Evidence:** open-source packages attract typosquats, malicious pull requests and compromised dependencies or CI.
- **Mitigation:** minimal dependencies; hash-pinned lockfile; pip-audit or osv-scanner in CI; branch protection and CODEOWNERS for sensitive modules; no untrusted-code workflows with secrets; PyPI trusted publishing and two-factor authentication; signed tags; `SECURITY.md`.
- **Verify by:** CI audits; review of workflow triggers; release dry-runs on TestPyPI.

### F12. Remote connector (conditional: only if built)
- **Evidence:** connectors need an internet-reachable HTTPS endpoint.
- **Mitigation:** opt-in and off by default; per-user scoped tokens; per-project isolation; unguessable IDs plus authorization checks; rate limits; short-lived relay storage; data-flow notice before enabling.
- **Verify by:** cross-tenant authorization tests; static scan.

### F13. Browser extension (conditional: separate repository, if ever built)
- **Mitigation:** host permissions limited to chat domains; click-triggered capture; no remote code or analytics; published permission rationale.
- **Verify by:** manifest permission audit; malicious-page message-spoofing test.

### F14. Reliability failures (Medium)
- **Evidence:** concurrent agents, crashes mid-write, schema evolution, silent trimming.
- **Mitigation:** SQLite transactions; atomic object writes; versioned schema with migrators and old-version fixtures; `critical` items never trimmed, with a loud failure when they cannot fit.
- **Verify by:** kill-during-write test, parallel savers, fixture migrations.

### F15. Privacy of the benchmark corpus (Medium)
- **Evidence:** real transcripts contain other people's data.
- **Mitigation:** consented transcripts only; scanner plus manual redaction audit before storage; sealed set access-controlled; publish derived metrics and hash manifests, not transcripts.
- **Verify by:** audit log of contributions and consent records.

### F16. Redaction evasion through obfuscation and retries (High)
- **Evidence (design):** an agent steered by injected text, or retrying clumsily after a `redaction_blocked` error, can split a secret across string literals, encode it (base64, hex, URL), reverse it, or hide it with zero-width characters. Detailed block messages also teach the agent what to avoid.
- **Mitigation:** scan bounded decoded variants (base64, hex, URL decoding, reversed text, joined string literals, Unicode normalization with zero-width characters removed), with size and time caps against decode bombs; an opaque-blob rule that flags long high-entropy or encoded-looking strings in prose fields and requires explicit human approval; minimal errors to agents (code and count only, detail to the CLI); a per-session circuit breaker for MCP saves that counts blocked attempts, stores no content or fingerprints, pauses the session after a threshold, logs `breaker_tripped`, and never blocks the CLI.
- **Residual risk:** evasion beyond the decoded variants remains possible; the human review step is the backstop. Thresholds need tuning from real usage.
- **Verify by:** seeded secrets transformed by each technique; decode-bomb fixtures; breaker state surviving restarts; breaker not affecting CLI saves; error messages containing no pattern names or positions.

### F17. Fence and hidden-character weaknesses (High)
- **Evidence (design):** models do not reliably respect delimiters, so an injected instruction inside the fence can still be followed (extends F1). Invisible characters (Unicode tag characters, bidirectional controls) can hide instructions from the reviewer, and a packet could imitate the tool's own risk summary.
- **Mitigation:** fence delimiter from a CSPRNG (`secrets.token_hex`, at least 128 bits), checked absent from content; strip Unicode tag characters and bidirectional override/embedding controls; flag, rather than strip, other invisible format characters (some scripts need joiners); visible provenance label on every rendered item; a tool-generated risk summary shown first in `show` (command-like lines, shell snippets, URLs, invisible characters, opaque blobs, unresolved conflicts), built from the tool's own scan and never from packet text; no bulk approval for T3 packets (explicit per-packet `--accept-untrusted`); `load_context` output uses the same fence and a leading notice that the content is data, not instructions; documentation tells users not to auto-approve agent tool calls while working with T2/T3 content.
- **Residual risk:** a model may still follow injected text. The real limit is what the agent is permitted to do, which is the IDE's permission model, not swallo's.
- **Verify by:** fence-breakout fuzzing; tag-character and bidi fixtures; a packet that imitates the risk summary; legitimate text with joiners surviving unchanged.

### F18. Agents ignore or overrule staleness warnings (Medium)
- **Evidence (design):** a soft warning relies on the receiving model to read and respect it; an agent may proceed and overwrite newer files with stale context.
- **Mitigation:** `stale.policy_mcp = block` by default for MCP loads (`warn` for human CLI sends). Critical drift is deterministic: a referenced file was modified, deleted or renamed, or the stamped commit is not an ancestor of HEAD. Unrelated commits stay silent so the block does not train users to disable it. Error `stale_context_blocked` names the drifted files. A human acknowledgment (`swallo approve <id> --target T --ack-stale`) is recorded in the ledger, bound to the packet hash, current HEAD and drifted-file hashes, and expires as soon as any of them changes.
- **Residual risk:** detects file changes, not changes in meaning.
- **Verify by:** temp repos covering an unrelated commit (no block), modified, renamed and deleted referenced files, a rebase that makes the commit a non-ancestor, and an acknowledgment that expires after a further change.

### F19. Draft spam and resource exhaustion (Medium)
- **Evidence (design):** an agent in a loop can call `save_context` hundreds of times; each packet may be within limits while the total bloats the store and floods the review queue. An injected agent could also fill its own quota to block legitimate saves.
- **Mitigation:** content-addressed deduplication (an identical payload returns the existing draft); a per-session token bucket with burst allowance and a global cap, persisted in SQLite, returning `rate_limited` with a retry time (MCP only, never CLI imports); quotas on unapproved MCP drafts per project by count and bytes; a TTL that purges unapproved MCP drafts, never approved or referenced packets; `swallo drafts purge` (CLI only, no delete tool in MCP); `list` collapses a loop's drafts into one series.
- **Residual risk:** thresholds need tuning; a flood can still fill a project's draft quota until a human purges.
- **Verify by:** a 500-call loop; identical-payload deduplication; quota fill followed by successful CLI saves; TTL leaving approved and referenced packets untouched; store growth bounded.

### F20. IDE configuration hijack and rogue data files (Medium)
- **Evidence (design):** a malicious pull request can add or change a workspace-level MCP config so the `swallo` command launches a different program. A repository can also ship its own `.swallo/handoff/` data file and stub without ever going through swallo.
- **Mitigation:** `init` prints global (user-level) setup only, with an absolute interpreter path rather than a bare command resolved through `PATH`; `doctor` scans workspace-level MCP configs for `swallo`-named commands and warns; the server serves only registered project roots (registry created by `init`) and returns `unregistered_project` otherwise; `doctor` warns about data files under `.swallo/handoff/` with no ledger record.
- **Residual risk:** a replaced command cannot police itself, so protection depends on user-level config and `doctor`; anything that can write the user's own config files is out of scope.
- **Verify by:** `doctor` on a workspace with a poisoned MCP config; a load from an unregistered root; a rogue data file in a test repo; the init snippet containing an absolute path.

### F21. Approval is weak against a compromised agent (High, partly accepted risk)
- **Evidence (design):** a terminal check does not prove a human is present (some agent shells use a pseudo-terminal), and the approval key is readable by the same user, so an agent with file access could compute valid approvals or re-initialize the store.
- **Mitigation:** baseline: best-effort terminal checks for `approve` and `init --force`; re-initializing an existing store requires `--force` and logs `store_reinit`; the limits are stated plainly in the documentation. Hardened tier (optional `[sign]` extra using `cryptography` with Ed25519, `approve.signing = passphrase`; the passphrase is stretched with `hashlib.scrypt`): a passphrase chosen at `init` and never stored derives a signing key; approvals and stale acknowledgments are signed; the store keeps only the public verification key; changing the signing mode or re-initializing requires the old passphrase.
- **Residual risk (accepted):** an agent with unrestricted file and shell access can replace the entire store even in the hardened tier. Full containment needs the IDE's sandbox and permission prompts.
- **Verify by:** attempting `approve` through a pseudo-terminal-wrapped subprocess; forging an approval from the key file; re-init without the passphrase in the hardened tier.

## 5. Secure defaults summary

Fail-closed redaction; redacted transcripts only; stdio-only MCP; two-file delivery; approval via TTY and local ledger; store outside the repo; restrictive permissions; no telemetry; no network in core; decoded-variant scanning; MCP circuit breaker; stale loads blocked for MCP; draft dedupe, quotas and TTL; global-only MCP setup with registered roots.

## 6. Prompt-injection claims policy

Never describe the tool as "injection-proof" or "leak-proof". Documentation states: what each control does, what it does not do, and what was measured. Model-dependent behavior is reported with model name and version.

## 7. Security testing plan and tools

| Step | Tools (verify names and features) |
|---|---|
| Secrets/PII | gitleaks, trufflehog, Presidio, over store/log/temp/errors |
| Static analysis | bandit, semgrep (paths, subprocess, deserialization, injection) |
| Dependencies | pip-audit, osv-scanner, OpenSSF Scorecard |
| Fuzz/property | Hypothesis, Atheris (loader, importers, resolver, fence) |
| MCP | An MCP inspector client; header/port tests for any HTTP mode |
| Agent injection | Sandboxed agents with no real secrets, results labelled model-dependent |
| Guards and limits | pytest and Hypothesis: 500-call save loop, deduplication, quota and TTL behavior, breaker persistence and scope, stale-policy temp repos, root registry, `doctor` on poisoned configs |
| Review | Independent human review of F1-F5 before v0.1 |

Process: for each finding run its test, record the result in the register, adjust status and severity, fix, retest, and keep the test as a regression.

## 8. Secure development lifecycle

- Security-sensitive modules require CODEOWNER review (`redact/`, `store/ledger.py`, `repo/paths.py`, `render/sanitize.py`, `capture/importers/`, `server/guards.py`, `store/registry.py`, `store/signing.py`).
- Security tests run in CI on every pull request.
- Dependency and workflow changes get explicit review.
- Release artifacts are built in CI and published via trusted publishing.
- The optional `[sign]` extra (`cryptography`) is imported lazily; CI runs the full suite with no extras installed, audits `cryptography` with pip-audit, and tests signing against known vectors.
- Guard thresholds are experimental in 0.x; every guard decision writes an event so thresholds can be tuned from real usage.

## 9. Incident response and disclosure

Private reporting channel in `SECURITY.md`; triage by severity; fix, release, and publish an advisory describing affected versions and mitigations. If a redaction miss is found, publish the pattern class and update benchmark recall numbers.

## 10. Residual risks (accepted and documented)

Model-dependent injection behavior; incomplete redaction on unknown formats; agents or attackers with unrestricted local file and shell access; reliance on third-party apps' handling of delivered text; limited recall of rule-based conflict detection; guard thresholds that need tuning from real usage; IDE-level behavior (workspace configs, tool-approval prompts) that swallo cannot control.
