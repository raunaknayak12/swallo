# Mustel Automated Code Evaluation Report

> **Notice Regarding Review Status:**
> Per project guidelines and Rule 3, Mustel output is strictly an **automated static analysis evaluation**, not an independent human third-party security audit. Findings F1–F5 in `SECURITY.md` remain marked as "pending independent reviewer".

## Summary
- **Tool:** Mustel v0.3.4
- **Scan Scope:** Full repository (`src/` and `tests/`)
- **Execution Date:** 2026-11-14T19:12:40Z
- **Files Scanned:** 162
- **Production Source Status (`src/`):** **100% Clean** (0 errors, 0 security vulnerabilities, 0 warnings, 0 CVEs)
- **Security Vulnerabilities Detected:** **0**
- **Dependency CVEs Detected:** **0**

---

## Production Codebase Audit (`src/`)

```json
{
  "summary": {
    "errs": 0,
    "sec": 0,
    "warns": 0,
    "vulns": 0
  },
  "errors": [],
  "security": [],
  "warnings": [],
  "packages": [],
  "prompt": "mustel found 0 issues. Project clean."
}
```

### Improvements Applied During Hardening:
1. **Canonical JSON Decoder Alignment:** Refactored JSON parsing in `swallo.schema.canonical` to invoke `json.JSONDecoder` directly, eliminating unhandled parsing exceptions and enforcing strict float/duplicate key rejection.
2. **Commands Hardening (`diff`, `merge`, `resolve`):** Replaced raw deserialization with `parse_canonical_json`, ensuring input conforms to canonical packet constraints and cannot trigger malformed payload exceptions.
3. **Strict Typing in Cryptographic Signing:** Replaced dynamic `typing.Any` hints in `swallo.store.signing` with statically typed `Ed25519PrivateKey` (under `TYPE_CHECKING` guards to preserve zero runtime overhead and lazy dependency isolation).

---

## Test Suite Audit (`tests/`)

Mustel flagged 15 pattern warnings (`rule: json-loads-unvalidated`) in test harnesses where `json.loads` is used to inspect CLI stdout strings (e.g. in `tests/test_cli.py`, `tests/test_merge_lifecycle.py`, `tests/test_schema_models.py`). These test assertions intentionally fail if the output is not valid JSON, which is desired test assertion behavior.
