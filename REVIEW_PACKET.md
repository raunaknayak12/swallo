# Swallo Security & Architecture Review Packet (v0.1)

This review packet is prepared for an independent human security reviewer conducting the external evaluation of the Swallo context handoff and defense system.

---

## 1. Scope of Review

Swallo is a local-first, zero-network utility designed to securely transfer conversational context, decisions, constraints, and debugging state from chat assistants (ChatGPT, Claude, Gemini) to agentic IDEs (Claude Code, Cursor, Antigravity).

### Primary Attack Surface
- **File Ingestion:** Parsing user-provided JSON, markdown, or chat export archives.
- **Redaction Engine:** Regex and entropy-based identification and masking of API keys, private keys, connection strings, tokens, and decoded obfuscations.
- **Trojan Source Sanitizer:** Defense against invisible control characters, zero-width spaces, and bidirectional Unicode overrides (CVE-2021-42574).
- **Delivery Stubs:** Writing rules files and data files under `.swallo/handoff/` without allowing path escapes, symlink traversals, or unreviewed rule overwrites.
- **Model Context Protocol (MCP) Server:** Guard layer managing per-session token buckets, draft storage quotas, and consecutive block circuit breakers.

---

## 2. Security Findings Summary (F1–F5)

| Finding | Vulnerability / Threat | Implemented Mitigation | Verification Reference | Status |
|---|---|---|---|---|
| **F1** | Arbitrary Code Execution / Prompt Injection via Rules File Override | Two-file delivery architecture (ADR-006): rules file receives only an immutable pointer stub with per-render random fences; full context resides in isolated `.swallo/handoff/` data file. | `src/swallo/render/fence.py`, `tests/test_fence.py` | **Pending Independent Reviewer** |
| **F2** | Secret Leaks via Obfuscated / Encoded Payloads | Recursive multi-layer decoding scanner (Base64, Hex, URL, Rot13, Reversal, Zero-Width) with caps: depth 3, 64KB input size, 200ms timeout. | `src/swallo/redact/decode_scan.py`, `tests/test_decode_scan.py` | **Pending Independent Reviewer** |
| **F3** | Invisible Trojan Source Attacks | Unicode sanitizer neutralizing bidirectional override marks (LRO, RLO, PDF), tag characters (U+E0000), and zero-width joiners. | `src/swallo/render/sanitize.py`, `tests/test_sanitize.py` | **Pending Independent Reviewer** |
| **F4** | Malicious Archive Exploits (Zip-Slip / Zip Bombs) | Strict archive extraction guardrails: rejection of absolute paths, `..` traversals, symlinks, archives with >10,000 members, >100:1 compression ratio, or >256MB uncompressed. | `src/swallo/capture/zip_stream.py`, `tests/test_importer_security.py` | **Pending Independent Reviewer** |
| **F5** | Autonomous Agent Self-Approval of Injected Payloads | Hard invariant (ADR-007): MCP server exposes zero approve tools. Approval requires an interactive TTY and records HMAC / Ed25519 signatures in local ledger. | `src/swallo/commands/approve.py`, `tests/test_mcp_server.py` | **Pending Independent Reviewer** |

*Note on Review Gate: The implementer cannot self-certify F1–F5. The gate item remains marked "pending independent reviewer".*

---

## 3. Threat Model Links

Detailed specifications and architectural rationale are documented in:
- [Threat Model & Security Design](docs/Security.md)
- [Architecture Decision Records (ADRs)](docs/DECISIONS.md)
- [Context Packet Schema](docs/PACKET_SCHEMA.md)
- [Technical Requirements Document (TRD)](docs/TRD.md)

---

## 4. How to Run Tests & Verification

### Local Test Execution
```bash
# Set up development virtual environment
python -m venv .venv
# Activate environment (.venv\Scripts\activate on Windows, source .venv/bin/activate on POSIX)
pip install -e ".[dev,sign,mcp]"

# Run full test suite
pytest -v

# Run lint and strict type checks
ruff check src tests
mypy src/swallo

# Run Mustel security static analysis
# (or use MCP mustel review / review_file)
```

### Clean-Install & Dependency Isolation Verification
```bash
# Core package import isolation test (zero optional deps loaded)
python -W error -c "import swallo; import sys; assert 'cryptography' not in sys.modules; assert 'mcp' not in sys.modules; print('Clean!')"

# Run doctor in isolated temporary environment
swallo init
swallo doctor
```

---

## 5. Known Limitations & Out-of-Scope Items

1. **Entropy Detector False Positives:** The Shannon entropy detector flags high-randomness strings (e.g. UUIDs, long base64 hashes). These are intentionally flagged for human review in `mask` mode.
2. **Zero-Network Invariant:** Swallo makes zero outgoing network calls in core operation. Remote HTTP mode (`[remote]` extra) is deferred to v0.2.
3. **Prompt Injection Defense Philosophy:** Swallo does not claim algorithmic prompt-injection detection; it enforces structural containment (fencing, data file isolation, mandatory human TTY approval).
4. **Windows Symlinks:** Symlink creation requires Windows Developer Mode / administrative privileges; POSIX file permission modes (0700/0600) fall back to user-profile ACLs on Windows (ADR-027).
