# Contributing

Thanks for helping. This project handles private conversation data, so changes are reviewed with extra care.

## Ground rules

- By contributing you agree your contributions are dual-licensed under both the MIT License and the Apache License, Version 2.0.
- Pure Python. New runtime dependencies need a written justification (see `docs/TRD.md`, dependency policy).
- No network access in the core. Optional features (`[remote]`) must be opt-in and off by default.
- Never log, print or store secret or transcript text in error paths. Tests enforce this.
- Security-sensitive modules (`redact/`, `store/ledger.py`, `repo/paths.py`, `render/sanitize.py`, `capture/importers/`, `server/guards.py`, `store/registry.py`, `store/signing.py`) require review from a code owner.

## Development setup

```
git clone <repo>
cd swallo
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check . && mypy src
```

## Testing policy

Every contribution must maintain high quality and regression safety:
- **Unit and Integration Tests:** Run `pytest` across Python 3.11, 3.12, and 3.13. All existing tests must pass with zero warnings (`python -W error`).
- **Property-Based Testing:** Parsers, canonical JSON serialization, and sanitization routines must include Hypothesis property-based tests.
- **Adversarial & ReDoS Guardrails:** Any new regex in `src/swallo/redact` must pass adversarial ReDoS testing under a hard 100ms timeout.
- **Coverage Invariant:** New code must maintain or improve overall test coverage. Blanket suppressions, skipif without justification, and xfail on production paths are prohibited.
- **Pre-Push Verification:** Run Ruff, Mypy strict (`mypy src/swallo`), and Bandit security checks prior to creating a pull request.

## Release process

Releases follow semantic versioning (`vMAJOR.MINOR.PATCH`) with strict supply-chain controls:
1. **Version Alignment:** Version must be synchronized across `pyproject.toml`, `src/swallo/__version__.py`, `CHANGELOG.md`, and the release tag.
2. **Automated CI Gate:** All CI matrix jobs (Linux, macOS, Windows across Python 3.11/3.12/3.13), CodeQL security-extended analysis, and Bandit scans must be green on the release commit.
3. **Trusted Publishing (OIDC):** Package builds and publishes are performed exclusively through GitHub Actions via PyPI Trusted Publishing with cryptographic build provenance attestations. Manual uploads using API tokens or Twine from developer machines are forbidden.
4. **Environment Approvals:** Publishing jobs are gated by required maintainer reviews in the `pypi` and `testpypi` GitHub environments.
5. **Rollback Policy:** PyPI releases are immutable. Defective releases must be yanked with a stated reason on PyPI and superseded by an immediate patch release.

## Pull requests

1. Open an issue first for non-trivial changes.
2. Add tests. Parsers and path handling need property-based or fuzz tests.
3. Update docs and `CHANGELOG.md`.
4. Schema changes need a version bump, a migrator and a fixture for the old version (`docs/PACKET_SCHEMA.md`).
5. Benchmark or security claims in docs must match what a test actually shows.

## Contributing benchmark data

Only consented, redacted transcripts. See `docs/BENCHMARKS.md` and `docs/templates/ANNOTATION_GUIDE.md`. Never include real secrets or personal data.

## Code of conduct

Please review and adhere to our [Code of Conduct](CODE_OF_CONDUCT.md) (Contributor Covenant v2.1). Violations can be reported to conduct@swallo.dev.
