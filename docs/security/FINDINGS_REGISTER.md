# Findings Register

Live tracking for threat-model findings. Update on every test run. Status values: `hypothesized`, `confirmed`, `refuted`, `mitigated`, `accepted-risk`. Change severity only when a result justifies it.

| ID | Finding | Est. severity | Test | Tool | Result | Status | Fix | Retest date |
|---|---|---|---|---|---|---|---|---|
| F1 | Untrusted text reaches instruction channels | High | Injection payload fixtures; fence-breakout fuzz; sandboxed agent run | Hypothesis/Atheris; agent sandbox | | hypothesized | Two-file delivery, fixed stub, random fence | |
| F2 | Approval state forgeable | High | Import packet claiming approval; edit after approval then deliver | pytest | | hypothesized | Local ledger bound to hash | |
| F3 | Trust metadata in-band | High | Import packet declaring itself trusted | pytest | | hypothesized | Tool-assigned trust tiers | |
| F4 | Path fields enable traversal | High | Traversal, symlink, absolute and Windows path fuzz | Hypothesis; semgrep | | hypothesized | Hash-addressed objects; shared resolver | |
| F5 | Redaction misses | High | Scan outputs on labelled corpus | gitleaks, trufflehog, Presidio | | hypothesized | Layered detectors, deny-list, preview | |
| F6 | Raw transcripts stored; accidental commits | Medium | Full flow in test repo; permission and git-status checks | pytest; gitleaks | | hypothesized | Redacted by default; store outside repo; ignore prompts | |
| F7 | Local server exposure | Medium | Spoofed Host/Origin; page fetch to localhost; bind check | scripts | | hypothesized | Stdio default; loopback; token; allow-list | |
| F8 | Import parser abuse | Medium | Zip-slip, bomb, huge/deep JSON | fixtures; fuzz | | hypothesized | Limits; streaming; no member-name paths | |
| F9 | Merge poisoning | Medium | Override-language fixtures; recall on real corpus | pytest | | hypothesized | No auto-supersede; flags; provenance display | |
| F10 | Output handling; log tampering | Medium | Escape/template payloads; edited log row | pytest | | hypothesized | Sanitizer; hash-chained log | |
| F11 | Supply chain | Medium | Dependency audit; workflow review; TestPyPI dry-run | pip-audit; osv-scanner; Scorecard | | hypothesized | Pins, CODEOWNERS, trusted publishing | |
| F12 | Remote connector (if built) | Conditional | Cross-tenant authz; rate limit; scan | scripts; semgrep | | hypothesized | Opt-in; scoped tokens; isolation | |
| F13 | Browser extension (if built) | Conditional | Manifest audit; spoofed messages | manual | | hypothesized | Minimal permissions; click-triggered | |
| F14 | Reliability failures | Medium | Kill during write; parallel savers; old-schema fixtures | pytest; Hypothesis | | hypothesized | SQLite transactions; atomic writes; migrators; critical flag | |
| F15 | Benchmark corpus privacy | Medium | Consent audit; redaction audit | manual; scanners | | hypothesized | Consent; audit; sealed access | |
| F16 | Redaction evasion via obfuscation and retries | High | Seeded secrets transformed (split, base64, hex, reversed, zero-width); decode-bomb fixtures; breaker persistence and scope | pytest; Hypothesis | | hypothesized | Decoded-variant scan; opaque-blob rule; circuit breaker; minimal errors | |
| F17 | Fence and hidden-character weaknesses | High | Fence-breakout fuzz; tag/bidi fixtures; risk-summary imitation; legitimate-joiner preservation | Hypothesis; pytest | | hypothesized | CSPRNG fence; strip tag/bidi; flag others; tool-generated risk summary; no bulk T3 approval | |
| F18 | Stale context ignored by agents | Medium | Temp repos: unrelated commit, modify/rename/delete referenced file, rebase; acknowledgment expiry | pytest | | hypothesized | Deterministic drift rule; block for MCP; expiring acknowledgment | |
| F19 | Draft spam and resource exhaustion | Medium | 500-call loop; dedupe; quota fill with CLI still working; TTL safety | pytest | | hypothesized | Dedupe; token bucket; quotas; TTL; CLI-only purge | |
| F20 | IDE config hijack and rogue data files | Medium | `doctor` on poisoned workspace config; unregistered-root load; rogue data file | pytest; scripts | | hypothesized | Global-only init; absolute paths; root registry; doctor checks | |
| F21 | Approval weak against a compromised agent | High (partly accepted) | Approve via pty-wrapped subprocess; forge approval from key file; re-init without passphrase | pytest; manual | | hypothesized | Terminal checks; re-init guard; optional passphrase-signed approvals; documented residual risk | |

## Per-run log

| Date | Finding | What was run | Outcome | Notes / link to artifacts |
|---|---|---|---|---|
| | | | | |
