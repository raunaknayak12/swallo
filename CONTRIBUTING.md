# Contributing

Thanks for helping. This project handles private conversation data, so changes are reviewed with extra care.

## Ground rules

- By contributing you agree your contributions are licensed under the MIT license.
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

## Pull requests

1. Open an issue first for non-trivial changes.
2. Add tests. Parsers and path handling need property-based or fuzz tests.
3. Update docs and `CHANGELOG.md`.
4. Schema changes need a version bump, a migrator and a fixture for the old version (`docs/PACKET_SCHEMA.md`).
5. Benchmark or security claims in docs must match what a test actually shows.

## Contributing benchmark data

Only consented, redacted transcripts. See `docs/BENCHMARKS.md` and `docs/templates/ANNOTATION_GUIDE.md`. Never include real secrets or personal data.

## Code of conduct

Be respectful and constructive. A formal code of conduct file should be added before public launch.
