# Packaging and Release (PyPI)

**Status:** Draft v0.1. Items marked "verify" depend on current PyPI/GitHub/tool behavior.

## 1. Naming

- Decided: distribution `swallo`, import name `swallo`, CLI command `swallo`.
- Before the first publish: check PyPI for the name and for similar existing names such as `swallow` (confusion and typosquat risk). Reserve the name early with a minimal first release after a TestPyPI dry-run.
- A shorter alias can be added later as a second entry under `[project.scripts]` if wanted.

## 2. Repository layout

```
swallo/
  pyproject.toml  README.md  LICENSE  CHANGELOG.md  SECURITY.md  CONTRIBUTING.md
  CODEOWNERS  .github/workflows/  src/swallo/  tests/  docs/
```

Use the `src/` layout so tests run against the installed package.

## 3. `pyproject.toml` (starting point)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "swallo"
dynamic = ["version"]
description = "Reviewable handoff of AI conversation context between chat agents and IDEs"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"                     # SPDX expression (PEP 639); verify your build backend version supports it
license-files = ["LICENSE"]
authors = [{ name = "TBD" }]
keywords = ["mcp", "context", "handoff", "ai", "agents"]
classifiers = [
  "Programming Language :: Python :: 3",
  "Topic :: Software Development",
  "Intended Audience :: Developers",
]
dependencies = ["pydantic>=2"]

[project.optional-dependencies]
mcp    = ["mcp"]                    # official Python MCP SDK (verify package name and API)
tokens = ["tiktoken"]               # approximate counts; verify offline behavior
pii    = ["presidio-analyzer"]      # heavy; optional
remote = ["mcp"]                    # plus HTTP transport extras as required (verify)
sign   = ["cryptography"]          # optional hardened approvals (Ed25519); imported lazily
dev    = ["pytest", "hypothesis", "coverage", "ruff", "mypy", "bandit", "pip-audit", "build", "twine"]

[project.scripts]
swallo = "swallo.cli:main"

[project.urls]
Homepage = "TBD"
Issues = "TBD"
Security = "TBD"

[tool.hatch.version]
path = "src/swallo/__init__.py"
```

## 4. Versioning

- SemVer for the package. During 0.x, minor versions may include breaking changes, documented in the changelog.
- `schema_version` is independent: a package release may support several schema versions via migrators.
- Every release records supported schema versions in release notes.

## 5. CI pipeline (GitHub Actions or equivalent)

On every pull request:
1. Lint and format check (ruff); type check (mypy, strict on core).
2. Tests on Linux, macOS, Windows and supported Python versions.
3. Security tests (forged approval, trust markers, traversal, injection fixtures, leak scan).
4. `bandit`, `pip-audit` (or `osv-scanner`); fail on known vulnerabilities per policy.
5. Build sdist and wheel; `twine check`.
6. Workflow safety: do not run untrusted pull-request code with access to secrets.
7. Core-only job: install with no extras (so `cryptography`, `mcp` and other optional packages are absent) and run the full suite, proving the core runs on the standard library plus Pydantic.

On version tag:
1. Rebuild in CI from the tag.
2. Publish to TestPyPI, smoke-test installation in a clean environment.
3. Publish to PyPI using **trusted publishing** (OIDC; no long-lived token stored; verify current setup steps).
4. Create a GitHub release with notes, checksums, and the generated JSON Schema file.

## 6. Account and repository hygiene

- Two-factor authentication for all maintainers on PyPI and the code host.
- Branch protection, required reviews, CODEOWNERS for sensitive modules.
- Signed tags; consider provenance attestations (verify current PyPI support).
- Hash-pinned lockfile for development and CI; dependency update bot with review.
- Minimal runtime dependencies (see dependency policy in `TRD.md`).

## 7. Release checklist

- [ ] Changelog updated; docs match behavior
- [ ] All findings with status `confirmed` are fixed or documented as accepted risk
- [ ] Schema fixtures for every released version load through migrators
- [ ] TestPyPI install and smoke test pass on all three OSes
- [ ] `swallo doctor` passes on a clean environment
- [ ] Version tagged and signed; release notes written
- [ ] Post-release: install from PyPI in a clean environment and run the quickstart

## 8. Support matrix and deprecation

Support each minor version of Python while it is supported upstream (verify dates at release time). Announce removals one minor release ahead. Yank only for serious defects, with a changelog note.

## 9. Extras and install experience

`pip install swallo` must work with no compiler and no network access at runtime. Missing optional extras give a clear message naming the extra to install.

## 10. License

MIT (decided). The `LICENSE` file is included in this pack; its copyright line reads "swallo contributors" and can be changed to a named holder. Include the file in sdist and wheel, and list third-party dependency licenses at release time.
