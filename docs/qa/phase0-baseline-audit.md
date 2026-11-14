# Phase 0 Baseline Audit — Swallo v0.1.3 Release Engineering

**Auditor:** Automated (Antigravity agent)
**Date:** 2026-11-13
**Branch under review:** `fix/0.1.3-qa-findings`
**Last commit on branch:** `f71c175` (docs: add FIX_REPORT_0.1.3.md for v0.1.3 release)
**Latest published PyPI version:** 0.1.2
**All numbers below are computed from actual command runs. No estimates.**

---

## 1. Repository State

### Branches
```
  feat/rigorous-unoverfitted-benchmarks
* fix/0.1.3-qa-findings         ← candidate
  main
  phase/2-deterministic-benchmarks
  phase/3-statistical-perf-benchmarks
  phase/4-quality-supply-chain
  phase/5-docs-benchmarks-page
```

### Tags (as of `git tag -l`)
```
v0.1.0
v0.1.1
v0.1.2
```
> No `v0.1.3` tag exists yet. Correct — to be created after the release gate.

### Commits ahead of `main` (17 commits on fix branch)
```
f71c175  docs: add FIX_REPORT_0.1.3.md for v0.1.3 release
a7709b4  fix(show): preserve legacy target aliases in json approvals for backwards compatibility
9a45cdc  docs: align README with v0.1.3 commands, MCP tools, and env vars
f167c7c  docs: add CLI reference generator and generated CLI_REFERENCE.md
2d0bb4b  docs: add CHANGELOG.md entry for v0.1.3
cbc9ff3  chore(release): bump version to 0.1.3
56996a6  ci: enable CI triggers for fix branches and maintain 3.11-3.15 matrix
9d6de1f  test(security): add zero-network AST verification test
9a5ab6d  test(e2e): add full flow regression test suite
22cf84d  feat(mcp): add verify_context tool and get_context alias
7f3e098  fix(prompt): clarify error message when -t is passed as ingestion title
f292488  fix(send): add --format markdown flag
56fb3a5  fix(config): support SWALLO_STORAGE_DIR alias and warn on unknown env vars
bd96a7c  fix(targets): normalize target names consistently across approve/send/show/ledger
79bdbba  fix(prompt): derive item kinds from Pydantic model, fix sample JSON schema compliance
36bb460  fix(status): decode SQLite BLOB bytes before JSON parsing, handle corrupt rows
7809c23  docs(qa): record PyPI 0.1.2 QA and integration verification report
```

---

## 2. Version Consistency

| Location | Value |
|---|---|
| `pyproject.toml` | 0.1.3 |
| `src/swallo/__init__.py` | 0.1.3 |
| `CHANGELOG.md` | [0.1.3] - 2026-11-13 |
| `python -m swallo version` | swallo 0.1.3 |

✅ All consistent.

---

## 3. Fresh Install & Import Check

```
# Installed via: python -m pip install -e ".[dev,sign,mcp]"
python -W error -c "import swallo; print('swallo version:', swallo.__version__)"
→ swallo version: 0.1.3
```

**Dependency isolation verified:**
```
cryptography   → NOT LOADED (correct)
tiktoken       → NOT LOADED (correct)
mcp            → NOT LOADED (correct)
requests       → NOT LOADED (correct)
httpx          → NOT LOADED (correct)
urllib.request → NOT LOADED (correct)
```

---

## 4. Lint / Static Analysis

### Ruff
```
python -m ruff check src tests
→ All checks passed!   (0 issues)
```

### Mypy
**BLOCKED on this machine:** AppLocker prevents the mypy DLL from loading.
```
Error: DLL load failed while importing mypy: An Application Control policy has blocked this file.
```
**Mitigation:** mypy runs in GitHub Actions CI (Linux) where AppLocker is not present. Must verify via CI before gate.

### Bandit (`-ll` = medium+ only, as configured in CI)
```
python -m bandit -r src/swallo -ll -q
→ No issues identified.   (Medium: 0, High: 0)
```

**Low-severity findings (17) — not CI failures, documented here:**
- **B311** (1 finding): `random` module usage in `bench/fixtures.py:120` for benchmark fixture generation — not cryptographic, appropriate use.
- **B404 + B603 + B607** (16 findings): `subprocess` calls in `bench/runner.py`, `commands/edit.py`, `commands/send.py`, `repo/gitstate.py`, `repo/staleness.py` — all call `git` with hard-coded paths and no user-controlled shell injection vector. Appropriate for a developer tool that reads git state.

No `# nosec` suppressions used anywhere. 0 lines skipped.

---

## 5. Test Suite (recomputed — do not trust FIX_REPORT_0.1.3.md numbers)

```
# Command (AppLocker excludes hypothesis native module):
python -m pytest -p no:hypothesispytest \
  --ignore=tests/test_fence.py \
  --ignore=tests/test_fence_fuzz.py \
  --ignore=tests/test_hash_and_ids.py \
  --ignore=tests/test_paths.py \
  -q

Result: 360 passed in 23.52s
```

**Additional hypothesis-only tests:** 22 collected in the 4 excluded files (blocked by AppLocker on this machine; run in CI on Linux where hypothesis._native loads cleanly).

**Codebase stats:**
- Source: 84 `.py` files, 12,045 lines (src/swallo)
- Tests: 53 `.py` files, 7,036 lines (tests/)

---

## 6. pip-audit (swallo project dependencies only)

```
python -m pip_audit --skip-editable .
→ No known vulnerabilities found
```

**Note on global env findings:** Running `pip_audit --skip-editable` without specifying the project reports findings in `pillow 12.3.0`, `pyarrow 18.1.0`, `pyasn1 0.6.4` — these are dependencies of `apache_superset` and other unrelated packages installed in the global Python environment. They are **not** dependencies of swallo. Swallo's only runtime dependency is `pydantic>=2.0.0` (no vulnerabilities found).

---

## 7. Existing Workflow Files

| Workflow | File | Status |
|---|---|---|
| CI (lint + test matrix) | `ci.yml` | Exists, SHA-pinned |
| Clean Install | `clean-install.yml` | Exists, SHA-pinned |
| CodeQL | `codeql.yml` | Exists, SHA-pinned |
| Scorecard | `scorecard.yml` | Exists, SHA-pinned |
| Release (Trusted Publishing) | `release.yml` | Exists, SHA-pinned |
| Bench | `bench.yml` | Exists |

**All `uses:` actions are pinned by full SHA** — confirmed.

**Missing:** `.github/dependabot.yml` — does not exist yet. Required for Phase 5.

---

## 8. Security Files

| File | Exists | Notes |
|---|---|---|
| `SECURITY.md` | ✅ | Has **TODO-security-contact** placeholder — must be replaced before release |
| `CONTRIBUTING.md` | ✅ | Complete |
| `docs/DECISIONS.md` | ✅ | Complete |
| `CODE_OF_CONDUCT.md` | ✅ | Contributor Covenant v2.1 |

---

## 9. MCP Tools (actual count vs docs)

**Registered in `create_mcp_server()`:**
1. `save_context`
2. `load_context`
3. `get_context` (alias for load_context, added in fix branch)
4. `verify_context` (read-only integrity check, added in fix branch)
5. `merge_contexts`
6. `diff`
7. `list_contexts`

**Total: 7 tools**

**Discrepancy:** The module docstring at line 1-13 of `mcp_server.py` says "Exposes 5 safe tools" and lists the original 5. The docstring was not updated when `get_context` and `verify_context` were added. This is a Phase 1-B documentation bug.

**No approve tool exposed.** ✅ The comment at line 11 ("Deliberately absent: NO approve tool (SR-06)") is accurate.

---

## 10. `--force` Flag Analysis (Phase 1-A concern)

```
swallo approve --force   # ships in the installed wheel
```

The `--force` flag bypasses `confirm_on_terminal()`, the interactive TTY barrier. It is:
- Registered as a CLI argument in `src/swallo/commands/approve.py:45`
- Conditionally skips the `confirm_on_terminal()` call at line 112
- **Present in the shipped wheel** — any process with shell access can call it without TTY

**Threat assessment:** An IDE agent that can spawn a subprocess can call `swallo approve <id> --force --target claude-code` non-interactively, bypassing the human approval barrier. This violates the security invariant documented in `docs/Security.md` F21.

**However**, the same `docs/Security.md` and `terminal.py:9` acknowledge:
> "compromised agents with local subshell access can allocate a PTY"

The flag was used in prior tests to simulate approval in automated testing. Per Phase 1-A rules, it must be replaced with a **test-only monkeypatch** mechanism that is not shipped.

---

## 11. `ide_agent_autoapprove` Config Key

Found in `config.py:44` as a `TrustSettings` field defaulting to `False`. It is never read anywhere else in the codebase — the field exists but has no effect. This is dead configuration that could mislead users into thinking it enables auto-approval. Must be investigated in Phase 1.

---

## 12. Workflow Triggers and Python Version Matrix

`ci.yml` test-matrix:
- OS: ubuntu, macos, windows
- Python: 3.11, 3.12, 3.13, 3.14 (experimental), 3.15 (experimental)
- `continue-on-error: true` for 3.14 and 3.15 ✅

Required required jobs (ubuntu/macos/windows × 3.11/3.12/3.13) will fail the CI. Experimental 3.14/3.15 are allowed to fail.

---

## 13. README Claims

The README badges link to live CI, CodeQL, and Scorecard. Badge claims:
- CI badge — links to actual workflow
- Clean Install badge — links to actual workflow
- CodeQL badge — links to actual workflow
- Scorecard badge — links to `api.securityscorecards.dev` (will show "unknown" until main branch push)
- PyPI version badge — will work after release

**No unverified numeric claims found** (e.g., no hardcoded coverage %, no "0 vulnerabilities" claim). ✅

---

## 14. Open Issues for Phase 1

| ID | Severity | Description |
|---|---|---|
| P1-A | HIGH | `--force` flag in shipped wheel bypasses TTY approval; replace with test-only monkeypatch |
| P1-B | LOW | MCP server docstring says "5 tools" — actually 7; update to reflect current tool set |
| P1-C | LOW | `SECURITY.md` has `TODO-security-contact` placeholder — replace with actual contact |
| P1-D | LOW | `ide_agent_autoapprove` config key exists but is never read — either wire it up or remove |
| P1-E | LOW | `dependabot.yml` missing — required for Phase 5 Scorecard |
| P1-F | LOW | `get_context`/`load_context` default target `claude_code` (underscore) in MCP server — should use canonical `claude-code` |
| P1-G | INFO | Mypy cannot run locally (AppLocker); must be verified via CI results before gate |

---

## PHASE 0 SUMMARY

| Check | Result |
|---|---|
| Branch / tag state | ✅ 17 commits ahead of main; no v0.1.3 tag yet |
| Version consistency | ✅ 0.1.3 everywhere |
| Zero-warning import | ✅ `python -W error -c "import swallo"` clean |
| Ruff | ✅ 0 issues |
| Mypy | ⚠️ BLOCKED by AppLocker locally — CI must verify |
| Pytest (360 non-hypothesis tests) | ✅ 360/360 passed |
| Bandit (medium+ severity) | ✅ 0 findings |
| pip-audit (swallo deps) | ✅ 0 findings (pydantic has no known CVEs) |
| Dependency isolation | ✅ No optional modules load on import |
| `--force` bypass in shipped wheel | ❌ **Phase 1-A must address** |
| MCP tool count vs docs | ⚠️ 7 tools registered; docstring says 5 |
| SECURITY.md contact | ⚠️ TODO placeholder |
| Dependabot | ❌ Missing |
| Workflow SHA pins | ✅ All actions pinned by SHA |

**STOPPING for approval before Phase 1.**
