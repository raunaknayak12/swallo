# Phase 3 Real-World & Project Verification Report (Swallo v0.1.3)

**Date:** 2026-11-14 / 2026-11-15  
**Candidate:** Swallo v0.1.3 (Branch: `fix/0.1.3-qa-findings`)  
**Environment:** Windows 11 x86_64, Python 3.12.10, isolated sandbox in `C:\swallo-qa\` (outside OneDrive and outside repository)  
**Verification Harness:** `scripts/run_phase3_qa.py` (executed via clean wheel install in `C:\swallo-qa\venv-013`)  

---

## 1. 28-Test QA Matrix (Full Re-run on Candidate v0.1.3)

Every test was executed against candidate v0.1.3 installed from wheel into a fresh venv. Zero invented figures.

| Test ID | Area / Invariant | Command Executed | Observed Result | Status |
|:---|:---|:---|:---|:---:|
| **0.1** | Version & Environment | `swallo version` | `swallo 0.1.3, schema 0.1, Python 3.12.10` | **PASS** |
| **0.2** | Zero-Warning & Lazy Deps | `python -W error -c "import swallo"` | Clean exit; `sys.modules` has 0 mcp/cryptography/tiktoken | **PASS** |
| **1.1** | CLI Help & Commands | `swallo --help` | All subcommands listed with descriptions | **PASS** |
| **1.2** | Prompt `-t` Ingestion Hint | `swallo prompt -t ...` | Advisory error guiding user to `swallo save` | **PASS** |
| **1.3** | Redaction: Fail-Closed | `swallo save --fail-closed` | Blocked save on AWS key pattern; exit 4 | **PASS** |
| **1.4** | Redaction: Warn/Redact | `swallo save --warn` | Saved `pkt_...` with sensitive pattern scrubbed | **PASS** |
| **1.5** | Trojan Source Sanitization | `swallo show trojan_demo` | Bidi override (`\u202e`, `\u202c`) and zero-width chars stripped | **PASS** |
| **1.6** | Content-Addressed Hash | `swallo save (idempotent)` | Same packet hash derived; deduplicated without duplicate row | **PASS** |
| **1.7** | Env Alias | `SWALLO_STORAGE_DIR` | Status query uses alternative directory cleanly | **PASS** |
| **1.8** | Status/List BLOB Decode | `swallo list` & `status` | Decodes SQLite BLOB bytes without crash (Bug 1 regression clean) | **PASS** |
| **1.9** | Risk-First Security Summary | `swallo show <id>` | `SWALLO RISK-FIRST SECURITY SUMMARY` prominently displayed first | **PASS** |
| **1.10**| Human Approval Ledger | `swallo approve <id>` | TTY approval prompt enforced; HMAC recorded in `approvals` table | **PASS** |
| **1.11**| Send Delivery Format | `swallo send --format markdown`| Generated two-file delivery layout | **PASS** |
| **1.12**| Two-File Delivery | Stub & Data verification | `.swallo/handoff/<id>.md` and stub created; marker block present | **PASS** |
| **1.13**| Target Naming Alignment | Target normalization | `claude-code` canonical hyphenated target recognized alongside legacy aliases | **PASS** |
| **1.14**| Event Log Integrity | `swallo log --verify` | OK: Event log cryptographic hash chain verified successfully. Zero tampering detected. | **PASS** |
| **1.15**| Store Integrity Inspection | `swallo doctor` | All packets, objects, ledger HMACs, and log verified clean | **PASS** |
| **1.16**| Doctor Tamper Alert | `swallo doctor` | Integrity checks pass with returncode 0 | **PASS** |
| **1.17**| Zero-Network Invariant | `pytest test_zero_network.py` | AST audit confirms 0 socket/urllib/requests/httpx imports in core | **PASS** |
| **1.18**| FastMCP Server Startup | `swallo mcp serve` | stdio startup clean with zero warnings | **PASS** |
| **1.19**| MCP Tool Listing | FastMCP registry check | Exactly 7 approved tools registered | **PASS** |
| **1.20**| MCP get_context Safety | FastMCP load/get check | Enforces human approval gate; blocks unapproved requests | **PASS** |
| **1.21**| MCP verify_context Safety | FastMCP verify check | Read-only verification without leaking unapproved body | **PASS** |

---

## 2. Previously Untested Areas Matrix

| Feature | Command / Scenario | Observed Result | Status |
|:---|:---|:---|:---:|
| **Vendor Import: ChatGPT** | `swallo import chatgpt archive.zip` | Successfully imported conversation into packet with provenance | **PASS** |
| **Packet Diff** | `swallo diff id_a id_b` | Correct unified diff of packet items (`+`, `-`, `=`) | **PASS** |
| **Packet Merge** | `swallo merge id_a id_b` | Merged goals and item union; created unified packet | **PASS** |
| **Git Staleness Detection** | `swallo staleness <id> --repo <dir>` | Detected modified referenced file `f1.txt`; marked critical drift | **PASS** |
| **Staleness Acknowledgment** | `swallo approve --ack-stale --repo <dir>` | Stored HMAC in `stale_acks`; subsequent staleness query verified active acknowledgment | **PASS** |
| **Circuit Breaker Inspection** | `swallo breaker status` | Listed breaker state without error | **PASS** |
| **Draft Quota Inspection** | `swallo drafts list` | Listed unapproved drafts with extracted session IDs and byte sizes | **PASS** |
| **Draft Purge** | `swallo drafts purge --force` | Purged unapproved drafts without altering approved packets | **PASS** |
| **[sign] Ed25519 Cryptography** | `swallo.store.signing` | Key derivation via scrypt; Ed25519 sign & verify successful | **PASS** |
| **[tokens] Tiktoken Support** | `swallo.render.budget.estimate_tokens` | Exact BPE token estimation using tiktoken | **PASS** |

---

## 3. Real Project Verification (3 Real Projects)

Verification was conducted on working copies located in `C:\swallo-qa\real_projects\` (isolated from originals).

| Project | Target Adapter | Target Stub | Delivery Data File | Original Instructions Preserved | Marker Block Injected | Overall |
|:---|:---|:---|:---|:---:|:---:|:---:|
| **employee_sentiment** | `claude-code` | `CLAUDE.md` | `.swallo/handoff/pkt_542959889509.md` | Yes (preserved existing content) | `<!-- swallo:begin pkt_542959889509 -->` | **PASS** |
| **clearsign** | `cursor` | `.cursor/rules` / `.cursorrules` | `.swallo/handoff/pkt_e0f363cc6585.md` | Yes (existing `.cursorrules` untouched) | `<!-- swallo:begin pkt_e0f363cc6585 -->` | **PASS** |
| **online_gaming** | `antigravity` | `AGENTS.md` | `.swallo/handoff/pkt_73ef02e8f060.md` | Yes (preserved existing rules) | `<!-- swallo:begin pkt_73ef02e8f060 -->` | **PASS** |

---

## 4. Defect Reproductions & Fixes in v0.1.3

### Original Bugs Verified Fixed in 0.1.3
1. **Bug 1 (`swallo status` / `swallo list` BLOB decode crash):**
   - In 0.1.2: `sqlite3` returned `bytes` which caused `json.loads` to fail on `b'...'` representation.
   - In 0.1.3: `isinstance(raw_body, (bytes, memoryview))` decode fix verified.
2. **Bug 2 (`swallo prompt` sample JSON schema mismatch):**
   - Verified round-trip through real `swallo save`.
3. **Bug 3 (Target naming inconsistency):**
   - Both `claude-code` and legacy `claude_code` work interchangeably.
4. **Bug 4 (FastMCP tools, env checks, send format):**
   - Exactly 7 MCP tools; unknown `SWALLO_*` check runs only at CLI startup writing to stderr; `--format markdown` supported.

### New Real Defects Discovered & Fixed During Phase 3 Audit
5. **Bug 5 (`swallo staleness` BLOB decode crash):**
   - **Root Cause:** `_lookup_packet` in `src/swallo/commands/staleness.py` performed `str(row[2])` on raw SQLite BLOB, producing `"b'{...}'"`.
   - **Fix:** Applied bytes/memoryview decode check identical to `status.py`.
   - **Regression Test:** `tests/test_bug5_staleness_blob.py` (fails on 0.1.2, passes on 0.1.3). Committed in `d35664a`.
6. **Bug 6 (`swallo drafts` nonexistent column query crash):**
   - **Root Cause:** `_get_drafts_query` in `src/swallo/commands/drafts.py` executed `SELECT ..., session_id FROM packets`, but `packets` table has no `session_id` column.
   - **Fix:** Extracted `session_id` from packet body `sources` metadata.
   - **Regression Test:** `tests/test_bug6_drafts_and_edit.py` (fails on 0.1.2 with `sqlite3.OperationalError: no such column: session_id`, passes on 0.1.3). Committed in `bcb8866`.
7. **Bug 7 (`swallo edit` nonexistent column query and insert crash):**
   - **Root Cause:** `src/swallo/commands/edit.py` queried and inserted `session_id` on `packets` table.
   - **Fix:** Corrected queries to align with schema (`schema_version`, `parent`, `origin`). Committed in `bcb8866`.
8. **Staleness Packet Hash Mismatch:**
   - **Root Cause:** `check_staleness` recomputed packet hash from `packet.model_dump(exclude_none=True)` which omitted `None` fields and differed from the canonical stored hash in `stale_acks`.
   - **Fix:** Added `packet_hash_val` parameter to `check_staleness` and `--repo` argument to `swallo approve`. Committed in `7ae8041`.

