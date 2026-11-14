# OpenSSF Best Practices Badge (Passing Level) Evidence Document

This document maps every Passing-level criterion from the [OpenSSF Best Practices Badge](https://www.bestpractices.dev/criteria) to concrete evidence in the Swallo repository.

---

## 1. Basics

| Criterion | Requirement Summary | Status | Evidence in Repository / URLs |
|:---|:---|:---:|:---|
| **description_good** | Project description describes what software does | **Met** | [README.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/README.md) (Header, "What is Swallo", and Core Mission) |
| **interact** | Clear mechanism for feedback and questions | **Met** | [CONTRIBUTING.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CONTRIBUTING.md), GitHub Issues: https://github.com/raunaknayak12/swallo/issues |
| **contribution** | Process for contributions explained | **Met** | [CONTRIBUTING.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CONTRIBUTING.md) (Pull Request workflow, setup) |
| **contribution_requirements**| Contribution requirements and testing rules | **Met** | [CONTRIBUTING.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CONTRIBUTING.md) ("Testing policy", code standards) |
| **license_location** | FLOSS license in standard root location | **Met** | [LICENSE](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/LICENSE), [LICENSE-MIT](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/LICENSE-MIT), [LICENSE-APACHE](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/LICENSE-APACHE) |
| **floss_license** | Software released as FLOSS | **Met** | Dual-licensed under MIT and Apache-2.0 |
| **floss_license_osi** | License is OSI-approved | **Met** | Both MIT and Apache-2.0 are OSI-approved |
| **documentation_basics** | Basic user documentation provided | **Met** | [README.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/README.md), [QUICKSTART.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/docs/QUICKSTART.md), [USER_GUIDE.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/docs/USER_GUIDE.md) |
| **documentation_interface**| External interfaces documented (CLI & MCP) | **Met** | [CLI_REFERENCE.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/docs/CLI_REFERENCE.md), [CLI_AND_MCP_SPEC.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/docs/CLI_AND_MCP_SPEC.md), [PACKET_SCHEMA.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/docs/PACKET_SCHEMA.md) |
| **sites_https** | Project sites use HTTPS | **Met** | Repository, PyPI, and documentation URLs in `pyproject.toml` and documentation all use `https://` |

---

## 2. Change Control

| Criterion | Requirement Summary | Status | Evidence in Repository / URLs |
|:---|:---|:---:|:---|
| **repo_public** | Publicly readable source code repository | **Met** | https://github.com/raunaknayak12/swallo |
| **repo_track** | Track individual changes and contributions | **Met** | Git history with conventional commits |
| **repo_interim** | Intermediate versions tracked | **Met** | All work developed on branches and committed sequentially |
| **repo_distributed** | Distributed version control system | **Met** | Git |
| **version_tags** | Releases identified by signed/annotated tags | **Met** | Annotated tags following SemVer (`v0.1.3`) |
| **release_notes** | Human-readable release notes / changelog | **Met** | [CHANGELOG.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CHANGELOG.md) |
| **release_notes_vulns** | Vulnerabilities documented in release notes | **Met** | [CHANGELOG.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CHANGELOG.md) ("Security" sections), [SECURITY.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/SECURITY.md) |

---

## 3. Reporting

| Criterion | Requirement Summary | Status | Evidence in Repository / URLs |
|:---|:---|:---:|:---|
| **report_tracker** | Issue tracker for defect reporting | **Met** | https://github.com/raunaknayak12/swallo/issues |
| **report_process** | Clear process for reporting bugs | **Met** | [CONTRIBUTING.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CONTRIBUTING.md) |
| **report_responses** | Response expectations documented | **Met** | [SECURITY.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/SECURITY.md) (48-hour response goal) |
| **report_archive** | Public, searchable issue history | **Met** | GitHub Issues archive |
| **vuln_report_private**| Private vulnerability reporting channel | **Met** | GitHub Private Vulnerability Reporting and email in [SECURITY.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/SECURITY.md) |
| **vuln_report_response**| Response timeframe for security reports | **Met** | [SECURITY.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/SECURITY.md) (48h acknowledgment, 7d preliminary assessment, 30d patch target) |

---

## 4. Quality

| Criterion | Requirement Summary | Status | Evidence in Repository / URLs |
|:---|:---|:---:|:---|
| **build** | Standard automated build process | **Met** | `pyproject.toml` with `hatchling`, built via standard `python -m build` |
| **build_common_tools** | Built using widely deployed FLOSS tools | **Met** | Python `build`, `pip`, `hatchling` |
| **test** | Automated test suite included | **Met** | `pytest` test suite with 420+ automated tests in `tests/` |
| **test_invocation** | Standard command to invoke tests | **Met** | `pytest` (documented in [CONTRIBUTING.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CONTRIBUTING.md)) |
| **test_most** | Comprehensive test coverage | **Met** | Unit, integration, and adversarial suites covering core logic |
| **test_policy** | Documented testing policy | **Met** | [CONTRIBUTING.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/CONTRIBUTING.md) ("Testing policy") |
| **test_continuous_integration**| CI runs tests on changes | **Met** | GitHub Actions ([ci.yml](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/.github/workflows/ci.yml)) across Ubuntu, macOS, and Windows |
| **warnings** | Zero-warning build and import policy | **Met** | CI enforces `python -W error -c "import swallo"` and clean linting |

---

## 5. Security

| Criterion | Requirement Summary | Status | Evidence in Repository / URLs |
|:---|:---|:---:|:---|
| **know_secure_design** | Secure design and architecture documented | **Met** | [ARCHITECTURE.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/docs/ARCHITECTURE.md), [Security.md](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/docs/Security.md) |
| **know_common_errors** | Defenses against common vulnerability classes | **Met** | ReDoS timeouts, Trojan Source bidi sanitization, terminal escape stripping, path sanitization |
| **crypto_published** | Only standard published cryptographic algorithms | **Met** | SHA-256, HMAC-SHA256, Ed25519, scrypt KDF (zero custom ciphers) |
| **crypto_algorithm_min**| Minimum 128-bit symmetric / SHA-256 hashing | **Met** | SHA-256 (256-bit hash), 256-bit local key, Ed25519 (128-bit security level) |
| **dynamic_analysis** | Dynamic testing and property-based analysis | **Met** | Hypothesis tests (`tests/test_fence_fuzz.py`), Atheris fuzzer (`tests/fuzz_atheris.py`) |
| **static_analysis** | Automated static code analysis | **Met** | CodeQL (`.github/workflows/codeql.yml`), Bandit, Ruff, Mypy strict in CI |
| **static_analysis_often**| Static analysis runs on every push / PR | **Met** | [ci.yml](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/.github/workflows/ci.yml) and [codeql.yml](file:///c:/Users/Raunak/OneDrive/Desktop/swallo-docs/swallo-docs/.github/workflows/codeql.yml) |
