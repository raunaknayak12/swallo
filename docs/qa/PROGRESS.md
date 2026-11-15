# Swallo Release Progress Tracker (v0.1.4)

| Step | Description | Status | Next Exact Command / Action | Evidence Link |
|---|---|---|---|---|
| **Setup** | Quota discipline, tracking docs, runbook | IN PROGRESS | Commit tracking docs, begin Step 1 | `docs/qa/PROGRESS.md`, `docs/qa/RELEASE_RUNBOOK.md` |
| **Step 1** | Tamper fix follow-ups, mutation preconditions, 200-loop, Dependabot hygiene | PENDING | Check wheel for shipped bench defect, add preconditions | — |
| **Step 2** | New-user validation workflow from PyPI across OSs, golden path, real terminal TTY | PENDING | Create `.github/workflows/new-user-validation.yml` | — |
| **Step 3** | Public claims audit, README limitations/troubleshooting, issue templates | PENDING | Audit text for "zero vulnerabilities", add issue templates | — |
| **Step 4** | Release decision, version bump to 0.1.4, CHANGELOG | PENDING | Bump version across pyproject.toml, __init__.py, docs | — |
| **Step 5** | TestPyPI dry run and remote smoke verification | PENDING | `gh workflow run testpypi.yml` | — |
| **Step 6** | Release Gate verification & quota check | PENDING | Verify gate checklist, ask maintainer quota | — |
| **Step 7** | Merge PR, push tag `v0.1.4`, approve PyPI environment | PENDING | `git tag -a v0.1.4 ... && git push origin v0.1.4` | — |
| **Step 8** | Post-publish verification from real PyPI & Launch Kit | PENDING | `pip install swallo==0.1.4`, yank 0.1.2 on PyPI | — |

*Last Updated: 2026-11-15T22:24:00+05:30*
