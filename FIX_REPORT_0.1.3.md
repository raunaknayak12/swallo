# Swallo v0.1.3 Fix & Release Verification Report

## Executive Summary
This report documents the resolution of all QA findings, bugs, and inconsistencies identified during the testing of `swallo` v0.1.2, preparing the codebase for the `v0.1.3` production release. All changes have been implemented on the `fix/0.1.3-qa-findings` branch, thoroughly tested, verified with Mustel static analysis guardrails, and pushed progressively to the remote repository (`https://github.com/raunaknayak12/swallo.git`).

---

## 1. Test Suite Baseline vs. Final Summary

| Metric | v0.1.2 Baseline | v0.1.3 Release | Delta / Status |
| :--- | :--- | :--- | :--- |
| **Passing Pytest Tests** | 341 tests | **360 tests** | +19 tests added, 0 failures (100% pass) |
| **End-to-End Lifecycle Flow** | Not automated | **Automated E2E Suite** | Full CLI + MCP packet lifecycle verified |
| **Zero-Network Verification** | Manual grep | **Automated AST Audit** | CI test guarantees no network imports in core |
| **Wheel / Sdist Install** | v0.1.2 on PyPI | **Clean 0.1.3 build verified** | Installed & validated in fresh isolated venv |
| **Mustel Static Review** | N/A | **Clean / 0 Errors** | Pre-commit guardrails satisfied |

---

## 2. Detailed Bug Fix Breakdown

### Bug 1: `swallo list` / `swallo status` Crash (High Severity)
- **Symptom:** In v0.1.2, running `swallo list` or `swallo status` after saving any packet failed with `swallo.errors.ValidationError: Malformed JSON: Expecting value: line 1 column 1 (char 0)`.
- **Root Cause:** In SQLite, the `packets.body` column stores raw canonical JSON bytes (`BLOB`). `status.py` called `str(r[5])`, converting raw bytes into Python repr format `"b'{...}'"`, which fails JSON parsing. Furthermore, corrupt rows crashed the entire table listing rather than gracefully degrading.
- **Fix:**
  - Safely decoded bytes/memoryview to UTF-8 in `src/swallo/commands/status.py`.
  - Added robust per-row exception handling: corrupted rows display as `<corrupt>` with their ID and hash while healthy rows continue to render cleanly.
  - Standardized BLOB handling across all commands reading `packets.body`.
- **Tests Added:** `tests/test_bug1_status_blob.py` (0, 1, 3 packets, corrupted row handling, project filtering).

### Bug 2: `swallo prompt` Schema Mismatch (Medium-High Severity)
- **Symptom:** `swallo prompt` instructed LLM agents to use item kinds (`'decision'`, `'constraint'`, `'architecture'`, `'dependency'`, `'note'`), but the underlying Pydantic model (`src/swallo/schema/models.py`) only accepted (`'decision'`, `'constraint'`, `'question'`, `'artifact_ref'`). Additionally, the prompt's sample JSON omitted required fields (`created_at`, `sources`).
- **Architectural Decision:** The Pydantic model (`Packet`, `Item`, `ItemKind`) is the single source of truth. Kinds and schema definitions in `src/swallo/capture/prompt.py` are now dynamically derived via `typing.get_args(ItemKind)` and `Packet.model_fields`.
- **Fix:**
  - Updated `src/swallo/capture/prompt.py` to dynamically inspect `ItemKind` and required `Packet` fields.
  - Aligned sample JSON in the prompt template to pass `swallo save` validation cleanly.
- **Tests Added:** `tests/test_bug2_prompt_schema.py` (dynamic kind validation, sample JSON parsing, CI schema drift snapshot).

### Bug 3: Target Name Normalization & Ledger Compatibility (Medium Severity)
- **Symptom:** `approve` defaulted to `claude_code`, `send` required `claude-code`, and `show` listed `claude_code`. Default approve-then-send workflows failed with `"not approved for target"`.
- **Fix:**
  - Created centralized `normalize_target(target: str) -> str` in `src/swallo/adapters/registry.py` converting underscores to hyphens and mapping common aliases (`claude_code` -> `claude-code`, `agy` -> `antigravity`).
  - Applied `normalize_target` consistently in `approve`, `send`, `show`, and `ledger.is_approved`.
  - Maintained backward compatibility in `is_approved()`: checks both canonical and legacy target names when reading old stores, verifying each row's cryptographic HMAC against the exact target string recorded.
  - Retained backwards-compatible target keys in `swallo show --json` output (`approvals["claude_code"] = approvals["claude-code"]`).
  - Added target validation against `list_supported_targets()` at approve time.
- **Tests Added:** `tests/test_bug3_target_normalization.py` (normalization logic, legacy ledger HMAC verification, CLI argument rejection).

### Bug 4a: Configuration & Environment Variable Usability (Low Severity)
- **Symptom:** Documented `SWALLO_STORAGE_DIR` was not recognized; only `SWALLO_HOME` was checked.
- **Fix:**
  - Added `SWALLO_STORAGE_DIR` as a supported environment variable alias for `SWALLO_HOME` in `src/swallo/config.py`.
  - Added diagnostic warning on startup when unknown `SWALLO_*` environment variables are detected (catching typos such as `SWALLO_STORE`).
- **Tests Added:** `tests/test_bug4a_env.py`.

### Bug 4b: `swallo send --format` Flag Support (Low Severity)
- **Symptom:** `swallo send` did not accept `--format markdown`, failing when users followed documented markdown export commands.
- **Fix:** Added `--format {auto,markdown,json}` flag to `src/swallo/commands/send.py`, defaulting to `auto` and enabling explicit markdown rendering.
- **Tests Added:** `tests/test_bug4b_send_format.py`.

### Bug 4c: FastMCP Server Tool Alignment (Low Severity)
- **Symptom:** The FastMCP server implemented `verify_packet` and `read_packet`, while specifications referenced `verify_context` and `get_context`.
- **Fix:**
  - Registered `verify_context` as a first-class MCP tool verifying packet integrity and cryptographic HMAC status.
  - Added `get_context` as an alias to `read_packet` in `src/swallo/server/mcp_server.py`.
- **Tests Added:** `tests/test_bug4c_mcp_tools.py`.

---

## 3. Security and Architectural Guarantees Preserved

1. **Zero-Network Core:**
   - Automated AST audit (`tests/test_zero_network.py`) asserts that `src/swallo` contains zero imports of `urllib.request`, `requests`, `httpx`, `aiohttp`, or `socket`.
2. **Fail-Closed Secret Redaction:**
   - High-entropy scanning, base64/hex decoding, and credential pattern detectors remain strictly enforced.
3. **HMAC Ledger Integrity & SHA-256 Content Addressing:**
   - Packet hashes and ledger chains are immutably verifiable. Tampering with packet rows or ledger events is reliably detected.
4. **Mandatory Human-TTY Approval Barrier:**
   - Non-interactive TTY bypasses remain prohibited; explicit user interaction is enforced unless running in automated test harnesses with explicit `--force` testing keys.

---

## 4. End-to-End and Clean Virtual Environment Verification

1. **Wheel and Source Distribution Build:**
   ```bash
   python -m build
   # Successfully built:
   # dist/swallo-0.1.3-py3-none-any.whl
   # dist/swallo-0.1.3.tar.gz
   ```
2. **Fresh Isolated Environment Installation:**
   - Created clean virtual environment at `swallo_fresh_venv`.
   - Installed `dist/swallo-0.1.3-py3-none-any.whl` and dependencies.
   - Executed full end-to-end integration test suite (`tests/e2e/test_full_flow.py`) against the installed wheel: **PASSED (100%)**.

---

## 5. Git Commit Cadence

All commits follow conventional commit specifications and have been progressively pushed to `origin/fix/0.1.3-qa-findings`:

1. `7809c23`: `docs(qa): record PyPI 0.1.2 QA and integration verification report`
2. `36bb460`: `fix(status): decode SQLite BLOB bytes before JSON parsing, handle corrupt rows`
3. `79bdbba`: `fix(prompt): derive item kinds from Pydantic model, fix sample JSON schema compliance`
4. `bd96a7c`: `fix(targets): normalize target names consistently across approve/send/show/ledger`
5. `56fb3a5`: `fix(config): support SWALLO_STORAGE_DIR alias and warn on unknown env vars`
6. `f292488`: `fix(send): add --format markdown flag`
7. `7f3e098`: `fix(prompt): clarify error message when -t is passed as ingestion title`
8. `22cf84d`: `feat(mcp): add verify_context tool and get_context alias`
9. `9a5ab6d`: `test(e2e): add full flow regression test suite`
10. `9d6de1f`: `test(security): add zero-network AST verification test`
11. `56996a6`: `ci: enable CI triggers for fix branches and maintain 3.11-3.15 matrix`
12. `cbc9ff3`: `chore(release): bump version to 0.1.3`
13. `2d0bb4b`: `docs: add CHANGELOG.md entry for v0.1.3`
14. `f167c7c`: `docs: add CLI reference generator and generated CLI_REFERENCE.md`
15. `9a45cdc`: `docs: align README with v0.1.3 commands, MCP tools, and env vars`
16. `a7709b4`: `fix(show): preserve legacy target aliases in json approvals for backwards compatibility`

---

## 6. Manual Release Instructions for Maintainer

To finalize and publish release `0.1.3`, run the following commands:

```bash
# 1. Switch to main and merge the verified fix branch
git checkout main
git merge --ff-only fix/0.1.3-qa-findings
git push origin main

# 2. Tag the release
git tag -a v0.1.3 -m "Release v0.1.3: bugfixes, schema alignment, and MCP tools"
git push origin v0.1.3

# 3. Build release distributions
python -m build

# 4. Upload to PyPI (using twine or API token)
python -m twine upload dist/swallo-0.1.3*
```
