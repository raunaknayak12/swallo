# Findings Register

Live tracking for threat-model findings. Update on every test run. Status values: `hypothesized`, `confirmed`, `refuted`, `mitigated`, `accepted-risk`. Change severity only when a result justifies it.

| ID | Finding | Est. severity | Test | Tool | Result | Status | Fix | Retest date |
|---|---|---|---|---|---|---|---|---|
| F1 | Untrusted text reaches instruction channels | High | Injection payload fixtures; fence-breakout fuzz; sandboxed agent run | Hypothesis/Atheris; agent sandbox | Pending Step 5 | hypothesized | Two-file delivery, fixed stub, random fence | |
| F2 | Approval state forgeable | High | Import packet claiming approval; edit after approval then deliver | pytest | Pass | mitigated | Local ledger bound to hash (HMAC-SHA256) | 2026-11-01 |
| F3 | Trust metadata in-band | High | Import packet declaring itself trusted | pytest | Pass | mitigated | Schema drops trust fields; tool-assigned tiers | 2026-11-01 |
| F4 | Path fields enable traversal | High | Traversal, symlink, absolute and Windows path fuzz | Hypothesis; pytest | Pass | mitigated | Hash-addressed objects; strict resolve_in_root | 2026-11-01 |
| F5 | Redaction misses | High | Scan outputs on labelled corpus | pytest | Pass | mitigated | Layered detectors (regex, entropy, denylist), keyed placeholders | 2026-11-01 |
| F6 | Raw transcripts stored; accidental commits | Medium | Full flow in test repo; permission and git-status checks | pytest | Pass | mitigated | Store outside repo; fail-closed by default | 2026-11-01 |
| F7 | Local server exposure | Medium | Spoofed Host/Origin; page fetch to localhost; bind check | scripts | Pending Step 6 | hypothesized | Stdio default; loopback; token; allow-list | |
| F8 | Import parser abuse | Medium | Zip-slip, bomb, huge/deep JSON | fixtures; fuzz | Pending Step 7 | hypothesized | Limits; streaming; no member-name paths | |
| F9 | Merge poisoning | Medium | Override-language fixtures; recall on real corpus | pytest | Pending Step 8 | hypothesized | No auto-supersede; flags; provenance display | |
| F10 | Output handling; log tampering | Medium | Escape/template payloads; edited log row | pytest | Pass | mitigated | Display sanitizer (strips ANSI/BiDi/tags); HMAC hash-chained log | 2026-11-01 |
| F11 | Supply chain | Medium | Dependency audit; workflow review; TestPyPI dry-run | pip-audit; osv-scanner | Pass | mitigated | Zero runtime deps (except pydantic); pinned actions; pip-audit in CI | 2026-11-01 |
| F12 | Remote connector (if built) | Conditional | Cross-tenant authz; rate limit; scan | scripts; semgrep | N/A | hypothesized | Opt-in; scoped tokens; isolation | |
| F13 | Browser extension (if built) | Conditional | Manifest audit; spoofed messages | manual | N/A | hypothesized | Minimal permissions; click-triggered | |
| F14 | Reliability failures | Medium | Kill during write; parallel savers; old-schema fixtures | pytest; Hypothesis | Pass | mitigated | SQLite BEGIN IMMEDIATE transactions; atomic writes; migrations | 2026-11-01 |
| F15 | Benchmark corpus privacy | Medium | Consent audit; redaction audit | manual; scanners | N/A | hypothesized | Consent; audit; sealed access | |
| F16 | Redaction evasion via obfuscation and retries | High | Seeded secrets transformed (split, base64, hex, reversed, zero-width); decode-bomb fixtures; breaker persistence and scope | pytest; Hypothesis | Pass | mitigated | Decoded-variant scan; opaque-blob rule; decode-bomb defense | 2026-11-01 |
| F17 | Fence and hidden-character weaknesses | High | Fence-breakout fuzz; tag/bidi fixtures; risk-summary imitation; legitimate-joiner preservation | Hypothesis; pytest | Pass | mitigated | Strip tag/bidi; flag invisible zero-width chars; tool-generated risk summary | 2026-11-01 |
| F18 | Stale context ignored by agents | Medium | Temp repos: unrelated commit, modify/rename/delete referenced file, rebase; acknowledgment expiry | pytest | Pending Step 5 | hypothesized | Deterministic drift rule; block for MCP; expiring acknowledgment | |
| F19 | Draft spam and resource exhaustion | Medium | 500-call loop; dedupe; quota fill with CLI still working; TTL safety | pytest | Pending Step 5 | hypothesized | Dedupe; token bucket; quotas; TTL; CLI-only purge | |
| F20 | IDE config hijack and rogue data files | Medium | `doctor` on poisoned workspace config; unregistered-root load; rogue data file | pytest; scripts | Pass | mitigated | Global store outside repo; root registry; doctor diagnostics | 2026-11-01 |
| F21 | Approval weak against a compromised agent | High (partly accepted) | Approve via pty-wrapped subprocess; forge approval from key file; re-init without passphrase | pytest; manual | Pass | mitigated | Terminal checks (CONIN$ / /dev/tty); force confirmation; documented residual risk | 2026-11-01 |

## Per-run log

| Date | Finding | What was run | Outcome | Notes / link to artifacts |
|---|---|---|---|---|
| 2026-11-01 | F2, F4, F5, F10, F14, F16, F17, F20, F21 | pytest tests/ -v (108 tests) | All 107 pass (1 skipped symlink) | Steps 0-4 of IMPLEMENTATION_PLAN.md verified |
