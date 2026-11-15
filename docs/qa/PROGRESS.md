# Swallo Release Progress Tracker (v0.1.4)

| Step | Description | Status | Next Exact Command / Action | Evidence Link |
|---|---|---|---|---|
| **Setup** | Quota discipline, tracking docs, runbook | COMPLETED | Tracker and runbook initialized and maintained | `docs/qa/PROGRESS.md`, `docs/qa/RELEASE_RUNBOOK.md` |
| **Step 1** | Tamper fix follow-ups, mutation preconditions, 200-loop, Dependabot hygiene | COMPLETED | All tamper mutations assert row change; 500-loop + 200-loop CI passed (3/3 OS) | CI run 43739260704, `docs/qa/MCP_BOUNDS.md` |
| **Step 2** | New-user validation workflow, golden path, error handling, FastMCP bounds | COMPLETED | `validate_new_user.py` verified; `.github/workflows/new-user-validation.yml` created | `scripts/validate_new_user.py`, `.github/workflows/new-user-validation.yml` |
| **Step 3** | Public claims audit, README limitations/troubleshooting, issue templates | COMPLETED | README hardened; SECURITY.md updated; bug report & feature request templates added | `README.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/` |
| **Step 4** | Release decision, version bump to 0.1.4, CHANGELOG | COMPLETED | Bumped to 0.1.4 in pyproject.toml, __init__.py; CHANGELOG updated; sdist/wheel built | `pyproject.toml`, `CHANGELOG.md`, `docs/CLI_REFERENCE.md` |
| **Step 5** | TestPyPI dry run and remote smoke verification | IN PROGRESS | `gh workflow run testpypi.yml -f version=0.1.4.dev1` | `.github/workflows/testpypi.yml` |
| **Step 6** | Release Gate verification & quota check | PENDING | Confirm gate table checklist and check quota % | `docs/qa/PROGRESS.md` |
| **Step 7** | Merge PR, push tag `v0.1.4`, approve PyPI environment | PENDING | `git tag -a v0.1.4 ... && git push origin v0.1.4` | `docs/qa/RELEASE_RUNBOOK.md` |
| **Step 8** | Post-publish verification from real PyPI & Launch Kit | PENDING | Run new-user-validation with source=pypi, yank 0.1.2 on PyPI | `docs/qa/RELEASE_RUNBOOK.md` |

*Last Updated: 2026-11-15T23:38:00+05:30*
