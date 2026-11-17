# Swallo Release Progress Tracker (v0.1.4)

| Step | Description | Status | Evidence Link |
|---|---|---|---|
| **Setup** | Quota discipline, tracking docs, runbook | ✅ COMPLETED | `docs/qa/PROGRESS.md`, `docs/qa/RELEASE_RUNBOOK.md` |
| **Step 1** | Tamper fix follow-ups, mutation preconditions, 200-loop, Dependabot hygiene | ✅ COMPLETED | CI run 43739260704, `docs/qa/MCP_BOUNDS.md` |
| **Step 2** | New-user validation workflow, golden path, error handling, FastMCP bounds | ✅ COMPLETED | `scripts/validate_new_user.py`, `.github/workflows/new-user-validation.yml` |
| **Step 3** | Public claims audit, README limitations/troubleshooting, issue templates | ✅ COMPLETED | `README.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/` |
| **Step 4** | Release decision, version bump to 0.1.4, CHANGELOG | ✅ COMPLETED | `pyproject.toml`, `CHANGELOG.md`, `docs/CLI_REFERENCE.md` |
| **Step 5** | TestPyPI dry run (`swallo==0.1.4.dev1`) via OIDC | ✅ COMPLETED | CI run 43745305164 |
| **Step 6** | Release Gate: quota check (43%), user "GO", all checks green | ✅ COMPLETED | PR #15 all checks passed |
| **Step 7** | Merge PR #15, push tag `v0.1.4`, approve PyPI environment | ✅ COMPLETED | Tag v0.1.4, [PyPI release](https://pypi.org/project/swallo/0.1.4/), [GitHub release v0.1.4](https://github.com/raunaknayak12/swallo/releases/tag/v0.1.4) |
| **Step 8a** | Post-publish validation harness fixes (PR #18, PR #19) | ✅ COMPLETED | PR #18 merged (isolate MCP store), PR #19 merged (fix init_store import) |
| **Step 8b** | Post-publish new-user-validation from real PyPI | ✅ COMPLETED | [Run 43943208093](https://github.com/raunaknayak12/swallo/actions/runs/43943208093) — ALL PASS (13/13) |
| **Step 8c** | PyPI yank 0.1.2 / 0.1.3 | ⏳ MANUAL — see instructions below | Maintainer clicks required |

## Manual Step Required: Yank old PyPI versions

You need to yank `0.1.2` (and optionally `0.1.3`) on PyPI. This cannot be done via CLI — it requires clicking through the PyPI web UI.

**Click-by-click instructions:**

1. Go to: https://pypi.org/manage/project/swallo/releases/
2. Click **0.1.2** row → **Options** → **Yank release**
   - Reason: `Superseded by 0.1.4: CLI routing fix, FastMCP bounds, security docs`
3. *(Optional)* Click **0.1.3** row → **Options** → **Yank release**
   - Reason: `Superseded by 0.1.4: tamper-mutation preconditions, new-user validation, security docs`

Yanked versions remain installable if pinned (`pip install swallo==0.1.2`) but `pip install swallo` will not resolve to them.

*Last Updated: 2026-11-17T21:04:00+05:30*
