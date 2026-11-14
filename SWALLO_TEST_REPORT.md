# Swallo (PyPI Package) QA & Integration Verification Report

- **Date:** 2026-11-13
- **Tester:** Antigravity QA + Integration Engineer
- **Package Tested:** `swallo` version **0.1.2** (installed directly from PyPI: `swallo-0.1.2-py3-none-any.whl`)
- **Environment:**
  - OS: Windows 11 (`Microsoft Windows NT 10.0.26200.0`)
  - Python: `3.12.10` (Isolated virtual environment `.venv`)
  - PyPI Dependencies: `mcp==1.30.0`, `pydantic==2.14.3`, `pydantic-core==2.50.4`, `uvicorn==0.54.0`
- **Overall Verdict:** **usable with caveats**

---

## 1. Executive Summary

The `swallo` PyPI package provides local-first, zero-network context packet lifecycle management with content-addressed SHA-256 storage, HMAC-keyed secret redaction, Trojan Source bidi sanitization, tamper-evident audit logging, and FastMCP stdio integration.

However, several critical bugs and doc-vs-reality mismatches were discovered:
1. `swallo list` / `swallo status` crashes with an unhandled `ValidationError` due to improper string conversion of raw SQLite BLOB bytes.
2. The schema emitted by `swallo prompt` instructs chat agents to use item kinds (`architecture`, `dependency`, `note`) that are rejected by `swallo save`'s Pydantic schema (`decision`, `constraint`, `question`, `artifact_ref`).
3. Inconsistent target naming conventions (`claude_code` with underscore vs `claude-code` with hyphen) cause cross-command approval checks between `swallo approve`, `swallo send`, and `swallo show` to fail unless explicitly worked around.
4. The environment variable documented as `SWALLO_STORAGE_DIR` is completely ignored by the code; the actual environment variable is `SWALLO_HOME`.

---

## 2. Test Results Matrix

| Test | Command Run | Expected | Actual | PASS/FAIL |
| :--- | :--- | :--- | :--- | :--- |
| **0.1 Environment Check** | `python --version` | Python $\ge$ 3.11 | Python 3.12.10 | **PASS** |
| **0.2 PyPI Installation** | `pip install swallo "swallo[mcp]"` | Clean install into isolated venv | Installed `swallo-0.1.2` + deps cleanly | **PASS** |
| **1.1 CLI Help & Imports** | `python -m swallo --help` & import check | Imports from `.venv\site-packages`, displays real commands | Imported from `site-packages\swallo\__init__.py`; 22 commands listed | **PASS** |
| **1.2 Redaction CLI Spec** | `swallo prompt -t "redaction test"` | Ingests text and creates packet | `error: unrecognized arguments: -t redaction test` (`prompt` only outputs prompt templates) | **FAIL (Doc Mismatch)** |
| **1.3 Redaction (Fail-Closed)** | `swallo save --fail-closed packet.json` | Blocks save when secrets are detected | Blocked with: `Error: Redaction blocked save: 2 sensitive pattern(s) detected` | **PASS** |
| **1.4 Redaction (Warn/Redact)** | `swallo save --warn packet.json` | Replaces plaintext secrets with keyed `[REDACTED:...]` markers | All 5 secret types redacted (AWS key, GitHub token, Bearer token, PEM key, base64 key) | **PASS** |
| **1.5 Trojan Source Sanitization** | `swallo show <id>` on packet with U+202E, U+202A, U+200B | Neutralize bidi overrides and detect zero-width characters | U+202E and U+202A stripped in display; U+200B dynamically flagged in Risk Summary | **PASS** |
| **1.6 Content-Addressed Determinism**| Ingest exact same packet twice | Identical SHA-256 hash and packet ID | `pkt_2436478c3ae0` and `sha256:2436...` matched bit-for-bit | **PASS** |
| **1.7 Storage Env Var** | `$env:SWALLO_STORAGE_DIR=...` | Point storage to test directory | Silently ignored; `swallo` exclusively reads `SWALLO_HOME` | **FAIL (Doc Mismatch)** |
| **1.8 Status / List Query** | `swallo list --project demo` | Display tabular list of stored packets and states | Unhandled exception: `ValidationError: Malformed JSON: Expecting value: line 1 column 1` | **FAIL (Bug)** |
| **1.9 Risk-First Show** | `swallo show pkt_2436478c3ae0` | Display risk summary first, then approvals and sanitized items | Risk summary displayed at top, approval status rendered, items sanitized | **PASS** |
| **1.10 Human Approval Workflow** | `swallo approve <id>` on interactive TTY | Require confirmation on `CONIN$` / `/dev/tty`, write to ledger | Prompted `[y/N]` interactively; generated HMAC `8949deec...` | **PASS** |
| **1.11 Send Delivery Format Flag** | `swallo send <id> --format markdown` | Deliver markdown handoff | `error: unrecognized arguments: --format markdown` | **FAIL (Doc Mismatch)** |
| **1.12 Two-File Delivery** | `swallo send <id> --to claude-code` | Deliver `.swallo/handoff/<id>.md` and `CLAUDE.md` stub | Delivered fenced handoff and updated `CLAUDE.md` stub | **PASS** |
| **1.13 Target Naming Consistency** | `approve` default (`claude_code`) vs `send` default (`claude-code`) | Seamless transition from approve to send | Default approve records `claude_code`; send checks `claude-code` and rejects packet | **FAIL (Bug)** |
| **1.14 Tamper Detection (Events)** | Modify SQLite row in `events` table | Detect broken HMAC chain | `Event #4 (saved): HMAC mismatch` detected | **PASS** |
| **1.15 Tamper Detection (Ledger)** | Modify SQLite MAC in `approvals` table | Reject tampered approval row | `is_approved()` returned `False` | **PASS** |
| **1.16 Tamper Detection (Packet)** | Modify SQLite body in `packets` table | Recalculated hash diverges from content ID | Hash discrepancy detected (`sha256:fd4f...` != `sha256:2436...`) | **PASS** |
| **1.17 Zero-Network Audit** | AST / Regex scan of all `.py` files in package | No socket/HTTP requests in core CLI | Only `urllib.parse.unquote` used; zero network sockets or outbound calls | **PASS** |
| **1.18 FastMCP Server Startup** | `python -m swallo mcp serve` | Launch stdio FastMCP server | Initialized over stdio successfully | **PASS** |
| **1.19 FastMCP Tools Inspection** | MCP `list_tools` | Verify claimed tools exist | Tools: `save_context`, `load_context`, `merge_contexts`, `diff`, `list_contexts` | **PASS** |
| **1.20 FastMCP Claimed Tools** | Call `get_context` and `verify_context` | Check claimed tool names | Neither exists (`load_context` replaces `get_context`; no `verify_context`) | **FAIL (Doc Mismatch)** |
| **1.21 FastMCP Save & Draft** | `save_context` tool call | Save unapproved draft | Created packet with state `draft` (`pkt_1e4b71d4a756`) | **PASS** |
| **2.1 Real Project Isolation** | Copy `Employee Sentiment Analysis` to test folder | Original remains untouched | Copied to `C:\...\swallo_qa_test\employee_sentiment_copy` | **PASS** |
| **2.2 Real Project Registration** | Register workspace in swallo SQLite | Project root registered | Registered `employee-sentiment` in `projects` table | **PASS** |
| **2.3 Chat Handoff Ingestion** | Ingest task handoff with fake GitHub token | Redact secret and store packet | `ghp_FAKE999...` redacted to `[REDACTED:GITHUB_TOKEN:6049f4cc]` | **PASS** |
| **2.4 MCP Context Fetch** | Call MCP `load_context` from agent | Return fenced content to agent | Retained nonce fence and delivered sanitized payload | **PASS** |
| **2.5 Task Implementation** | Implement GDPR pseudonymization in `data_prep.py` | Working feature without secret leak | Implemented `anonymize_sender_emails()`, unit tested, verified 0 secret leaks | **PASS** |
| **2.6 Mustel Code Quality Audit**| `mustel review_file` on modified file | 0 errors, 0 security issues | Cleaned typing and imports; Mustel verified 0 errors, 0 security warnings | **PASS** |

---

## 3. Bugs Found (with Reproduction Steps)

### Bug 1: `swallo list` / `swallo status` Crashes with Malformed JSON `ValidationError`
* **Severity:** High (Core CLI Broken)
* **Location:** `swallo/commands/status.py:86` and `swallo/commands/status.py:106-115`
* **Reproduction Steps:**
  1. Ingest any valid packet: `python -m swallo save --warn packet.json`
  2. Run `python -m swallo list` or `python -m swallo status`
* **Observed Result:**
  ```text
  swallo.errors.ValidationError: Malformed JSON: Expecting value: line 1 column 1 (char 0)
  ```
* **Root Cause:**
  In `status.py:86`, the query returns `body` as SQLite `BLOB` (`bytes`). The code executes:
  ```python
  pkt_id, pkt_hash, proj, created_at, body_raw = str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4])
  ```
  `str(bytes_object)` converts `b'{"items":...}'` into the literal string `"b'{\"items\":...}'"`. When passed to `parse_canonical_json()`, JSON parsing fails on the leading `'b'`. Additionally, the exception handler catches `(ValueError, TypeError, KeyError)`, but `parse_canonical_json` raises `swallo.errors.ValidationError`, causing an unhandled crash.

---

### Bug 2: `swallo prompt` Schema Contradicts `swallo save` Validation
* **Severity:** Medium-High (Agent Handoff Broken)
* **Location:** `swallo/commands/prompt.py` vs `swallo/schema/models.py:Item`
* **Reproduction Steps:**
  1. Run `python -m swallo prompt --json` to inspect the prompt schema template given to chat agents.
  2. Observe the instruction:
     `"Valid item kinds are strictly: 'decision', 'constraint', 'architecture', 'dependency', 'note'"`
  3. Generate a packet adhering to that prompt and save it with `swallo save packet.json`.
* **Observed Result:**
  ```text
  pydantic_core._pydantic_core.ValidationError: 3 validation errors for Packet
  items.2.kind
    Input should be 'decision', 'constraint', 'question' or 'artifact_ref' [type=literal_error, input_value='architecture']
  ```
* **Root Cause:**
  `Item.kind` in `swallo.schema.models` is typed as `Literal['decision', 'constraint', 'question', 'artifact_ref']`. The prompt template was never updated to match the model schema. Additionally, `swallo prompt`'s sample JSON omits required fields `created_at` and `sources`.

---

### Bug 3: Inconsistent Target Naming Across Commands (`claude_code` vs `claude-code`)
* **Severity:** Medium (Approval Ledger Drift)
* **Locations:**
  - `swallo/commands/approve.py:33`: `default="claude_code"` (underscore)
  - `swallo/commands/send.py:161`: checks `is_approved(conn, key_bytes, p_hash, adapter.name)` where `adapter.name` is `"claude-code"` (hyphen)
  - `swallo/commands/show.py:124`: `known_targets = ["claude_code", "cursor", "antigravity"]` (underscore)
  - `swallo/store/ledger.py:is_approved`: performs raw string comparison without normalization.
* **Reproduction Steps:**
  1. Ingest a packet: `swallo save --warn packet.json` -> `pkt_abc`
  2. Approve using default settings: `swallo approve pkt_abc` (approves `"claude_code"`)
  3. Deliver packet: `swallo send pkt_abc` (checks `"claude-code"`)
* **Observed Result:**
  `Error: Packet 'pkt_abc' is not approved for target 'claude-code'.`
  Conversely, if approved with `--target claude-code`, `swallo send` succeeds, but `swallo show pkt_abc` continues to display `[NOT APPROVED] claude_code`.

---

### Bug 4: Windows WDAC / AppLocker Blocks `.exe` Wrappers in Virtual Environment
* **Severity:** Low-Medium (Platform-Specific)
* **Environment:** Windows Defender Application Control / AppLocker
* **Reproduction Steps:**
  1. Create a venv and run `.venv\Scripts\swallo.exe --help`.
* **Observed Result:**
  `Program 'swallo.exe' failed to run: An Application Control policy has blocked this file.`
* **Workaround:**
  Running via Python module `python -m swallo <args>` works reliably.

---

## 4. Doc-vs-Reality Mismatches

1. **Storage Environment Variable:**
   * *Claimed:* `SWALLO_STORAGE_DIR`
   * *Reality:* Only `SWALLO_HOME` is read by `swallo/config.py`. `SWALLO_STORAGE_DIR` is silently ignored.
2. **Text Ingestion via `swallo prompt`:**
   * *Claimed:* Piping text into `swallo prompt -t "title"` ingests and redacts content.
   * *Reality:* `swallo prompt` does not accept `-t` and does not ingest data; it only formats instruction prompts for chat agents. Ingestion is handled by `swallo save [file]`.
3. **Delivery Format Flag:**
   * *Claimed:* `swallo send <id> --format markdown`
   * *Reality:* `swallo send` rejects `--format`. Delivery is controlled by `--to` / `-t` (e.g. `claude-code`, `antigravity`, `chat`) and always outputs markdown files with CSPRNG fences.
4. **FastMCP Tools:**
   * *Claimed:* `list_contexts`, `get_context`, `save_context`, `verify_context`.
   * *Reality:* Registered tools are `save_context`, `load_context`, `merge_contexts`, `diff`, and `list_contexts`. There is no `get_context` or `verify_context`.

---

## 5. Missing Features

1. **`verify_context` MCP Tool:** The MCP server lacks a verification tool, forcing IDE agents to load packets blindly without verifying cryptographic ledger MACs or event log chains beforehand.
2. **Target Normalization in Approval Ledger:** `is_approved()` and `approve()` should normalize target strings (e.g. mapping `claude_code` to `claude-code`) so CLI approval flags and adapter targets do not mismatch.
3. **Direct Raw Text Ingestion:** `swallo save` requires a structured JSON packet conforming to Pydantic models. A `swallo ingest --text` or stdin pipe tool to automatically generate a basic envelope from raw text would dramatically improve usability.

---

## 6. One-Line Final Verdict

> **Verdict: usable with caveats** — Swallo's cryptographic core, secret redaction engine, tamper-evident audit logging, and FastMCP delivery pipeline are rock-solid, but broken listing commands (`swallo list`), conflicting prompt-to-save schemas, and target-naming bugs require explicit workarounds.

