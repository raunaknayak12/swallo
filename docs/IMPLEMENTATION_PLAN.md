# Implementation Plan

**Status:** Draft v0.1 | **Date:** 2026-10-25 | Companion docs: `TRD.md`, `PACKET_SCHEMA.md`, `Security.md`, `ROADMAP.md`, `DECISIONS.md`

`ROADMAP.md` lists milestones. This document is the engineering sequence: what to build first, in what order, with interfaces, tests and exit criteria for each step. No code exists yet; everything here is a plan.

## 1. Scope of the first build

**In scope (Steps 0-7):** schema and hashing, SQLite store and object store, safety spine (sanitizer, path resolver, event log, ledger, redaction), CLI with help, delivery v0 (Claude Code and chat briefing), merge, then the MCP server with guards and staleness.

**Out of scope until the core is stable:** HTTP/remote mode and the `[remote]` extra, the benchmark harness, importers (Step 8), the optional `[sign]` implementation (Step 8), the browser extension, and the Cursor and Antigravity adapters until each IDE spike is done.

## 2. Settled decisions (details in `DECISIONS.md`)

| Decision | ADR |
|---|---|
| Canonical JSON: own definition, no floats, golden-tested; hashed form excludes volatile fields | ADR-024 |
| Packet IDs derived from the hash | ADR-025 |
| Store-location helper in stdlib; config read with `tomllib` | ADR-026 |
| Best-effort permissions on Windows | ADR-027 |
| Guard thresholds are experimental config defaults, tuned later | ADR-028 |
| IDE behavior verified during integration, with per-project fallback | ADR-029 |
| `cryptography` for the optional `[sign]` extra, lazily imported | ADR-030 |
| Core CLI and SQLite store first; build order below | ADR-031 |

## 3. Working agreements

- Every step ends with green CI on all three operating systems and its "done when" tests.
- No new runtime dependency without a written justification. Optional extras are imported lazily; CI runs the full suite with no extras installed.
- Security-sensitive modules need CODEOWNER review: `redact/`, `store/ledger.py`, `repo/paths.py`, `render/sanitize.py`, `capture/importers/`, `server/guards.py`, `store/registry.py`, `store/signing.py`.
- Errors never echo secrets or transcript text. A test enforces this.
- Every guard decision (block, rate limit, breaker trip, stale block) writes an event so thresholds can be tuned later.
- Docs change in the same pull request as behavior. Any benchmark or security claim must match what a test shows.
- One concern per pull request; add tests with the change.

## 4. Step 0: Scaffold

**Goal:** a repository where CI is green and `swallo version` runs.

Tasks:
1. Create the repo with `src/swallo/`, `tests/`, `docs/` (this pack), `LICENSE` (MIT), `CODEOWNERS`.
2. `pyproject.toml` with hatchling, `requires-python = ">=3.11"`, `dependencies = ["pydantic>=2"]`, extras (`mcp`, `tokens`, `pii`, `remote`, `sign = ["cryptography"]`, `dev`), and `[project.scripts] swallo = "swallo.cli:main"`.
3. Tooling configuration (starting point):

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "S"]   # S = bandit-style security rules

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src/swallo"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = ["posix_only: skipped on Windows", "slow: long-running"]
```

4. CI jobs: lint and types; tests on Linux, macOS, Windows across Python versions still supported upstream; a **core-only** job that installs with no extras; `pip-audit`; build and `twine check`.
5. `swallo version` prints the version from `swallo/__init__.py`.
6. Confirm `swallo` is available on PyPI and check similar names (for example `swallow`). Consider reserving the name with a TestPyPI dry-run followed by a minimal release.

**Done when:** CI is green on all jobs; `pip install -e .` gives a working `swallo version`; the name check is recorded in `DECISIONS.md`.

## 5. Step 1: Schema and hashing

**Files:** `schema/models.py`, `schema/canonical.py`, `schema/limits.py`, `schema/jsonschema.py`, `errors.py`.

**Interfaces (stubs):**

```python
# schema/canonical.py
def canonicalize(value: object) -> bytes: ...            # swallo canonical JSON v1
def hashed_form(packet: dict) -> dict: ...               # drops id, created_at, sources[*].captured_at
def packet_hash(packet: dict) -> str: ...                # "sha256:<hex>"
def derive_packet_id(hash_: str, taken: set[str] | None = None) -> str: ...   # "pkt_" + 12 hex, extend on collision
def derive_item_id(kind: str, text: str, taken: set[str] | None = None) -> str: ...  # proposal: "it_" + 8 hex
```

**Canonical rules to implement** (see `PACKET_SCHEMA.md` section 6): UTF-8, sorted keys, no whitespace, duplicate keys rejected, strings NFC-normalized at ingest, integers only within +/-(2^53 - 1), floats/NaN/Infinity rejected anywhere.

**Models:** `Packet`, `Source`, `Transcript`, `Goal`, `Item`, `Provenance`, `Conflict`, `RepoState`, `Redaction`, with the limits from `PACKET_SCHEMA.md` section 7. Trust fields in incoming data are ignored.

**Tests:**
- Golden files: canonical bytes and hash for a fixture per schema version.
- Property: key order does not change the hash; changing any hashed field changes it; changing a volatile field does not; canonicalization is idempotent; NFC normalization is idempotent; floats and duplicate keys are rejected.
- Limits: oversized, deeply nested, malformed JSON are rejected with field-level errors.
- JSON Schema export matches the committed file.

**Done when:** all of the above pass, and a changelog note records that any canonicalization change requires a schema major bump.

## 6. Step 2: Store

**Files:** `config.py`, `store/db.py`, `store/objects.py`, `store/registry.py`; the `init` command's core.

**Store location helper (stdlib only):**

| OS | Default directory |
|---|---|
| Linux and other POSIX | `$XDG_DATA_HOME/swallo`, else `~/.local/share/swallo` |
| macOS | `~/Library/Application Support/swallo` |
| Windows | `%LOCALAPPDATA%\swallo` (not roaming `%APPDATA%`, so sensitive data is not synced between machines) |

Overrides: the `SWALLO_HOME` environment variable and `--store`. `doctor` warns if the store is inside a git work tree. Config lives at `<store>/config.toml`, read with `tomllib` and validated by a Pydantic `Config` model; `init` writes it from a template (no TOML writer needed). Unknown keys produce a warning.

**SQLite rules:** open with `isolation_level=None` and manage transactions explicitly (`BEGIN IMMEDIATE` for writers); `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, a `busy_timeout`; schema versioned with `PRAGMA user_version` and numbered migration files applied in a transaction. `synchronous` starts at `NORMAL` (proposal; revisit if durability matters more than speed).

**Object store:** `put(data, kind) -> hash`, `get(hash)`. Write to a temp file in the destination directory, `fsync`, `os.replace`, then `fsync` the directory on POSIX.

**Key file:** 32 random bytes from `secrets.token_bytes`, created with `O_CREAT | O_EXCL` and mode `0600`.

**Permissions:** POSIX directories `0700`, files `0600`. Windows: best effort, relying on the user-profile ACLs; `doctor` reports permission checks as best effort there.

**Tests:** parallel writers (multiprocessing) never corrupt state; a process killed mid-write leaves no partial object or half-applied row; object round trips; location helper under mocked environments; config parsing with unknown keys; migration from empty to current; permission checks marked `posix_only`.

**Done when:** all pass and `swallo init` creates a store, key, config and project registry entry on all three operating systems.

## 7. Step 3: Safety spine

**Order:** sanitizer, path resolver, event log, ledger, redaction v0, decoded-variant scanning.

**Files and interfaces (stubs):**

```python
# render/sanitize.py
def sanitize_for_display(text: str, max_len: int = 2000) -> str: ...  # strip control/escape sequences, tag chars, bidi controls
def flag_invisible(text: str) -> list[str]: ...                       # report zero-width/joiner characters, not stripped

# repo/paths.py
def resolve_in_root(root: Path, rel: str) -> Path: ...  # rejects absolute, "..", symlink escapes

# store/eventlog.py
def append(conn, type: str, packet_hash: str | None, target: str | None, detail: str) -> None: ...
def verify(conn) -> list[str]: ...     # mac_i = HMAC(key, prev_mac || canonical(row without mac))

# store/ledger.py
def approve(conn, packet_hash: str, target: str) -> None: ...       # mac over "approval\0hash\0target\0time"
def is_approved(conn, packet_hash: str, target: str) -> bool: ...

# redact/engine.py
class Detector(Protocol):
    name: str
    def scan(self, text: str) -> Iterable[Finding]: ...
def redact(text: str, mode: Literal["fail_closed", "warn"]) -> RedactionResult: ...
```

**Terminal confirmation:** `confirm_on_terminal(prompt)` reads the answer from the controlling terminal (`/dev/tty` on POSIX, `CONIN$` on Windows), not from stdin, so piped input cannot answer it. Best effort, not proof of a human (Security F21).

**Redaction v0:** built-in patterns, entropy detector, deny-list, keyed placeholders (`[REDACTED:<type>:<keyed-short-hash>]`); then decoded-variant scanning (bounded depth, size and time caps), the opaque-blob rule, and minimal agent-facing errors.

**Tests:**
- Forged-approval packet (claims approval) is not treated as approved; edit after approval requires re-approval.
- A tampered or deleted log row fails `verify`.
- Seeded secrets (plain and transformed: split, base64, hex, URL-encoded, reversed, zero-width) do not appear in the store, log or error output (scan with the project's own scanner and, if installed, gitleaks).
- Decode-bomb inputs finish within caps.
- Sanitizer fixtures: tag characters, bidi controls, escape sequences removed; zero-width and joiner characters flagged; legitimate joiner text unchanged.
- Path resolver properties: no result escapes the root, including through symlinks.

**Done when:** these pass and an independent review of F2-F5 and F10 is scheduled.

## 8. Step 4: CLI and help

**Files:** `cli.py`, `help.py`, `commands/` (one module per command), `errors.py` (exceptions carry exit codes).

**Single source of truth for commands:**

```python
@dataclass(frozen=True)
class Command:
    name: str
    group: str
    summary: str
    usage: str
    description: str
    options: tuple[tuple[str, str], ...]
    examples: tuple[str, ...]
    exit_codes: tuple[tuple[int, str], ...]
    handler: Callable[[argparse.Namespace], int]
```

`cli.py` builds the `argparse` tree from the registry; `help.py` renders the overview, per-command help and topics from the same registry (`flows`, `exit-codes`, `config`, `security`). Unknown commands exit 2 with `difflib.get_close_matches` suggestions.

**Commands in order:** `help`, `version`, `init`, `doctor`, `save`, `show`, `approve`, `list`, `status`, `log`. Output is human-readable by default and machine-readable with `--json`.

**Tests:** every registered command has help text, at least one example and listed exit codes; help output golden files; exit-code mapping; end-to-end flow through a subprocess in a temporary store (`SWALLO_HOME`); a fixture that blocks network sockets proves the core makes no network calls; `--json` outputs match documented keys.

**Done when:** a user can `init`, `save` a pasted packet, `show` it with a risk summary, `approve` it, and see it in `log`, entirely offline.

## 9. Step 5: Delivery v0

**Files:** `render/briefing.py`, `render/claude_md.py`, `render/fence.py`, `render/budget.py`, `adapters/base.py`, `adapters/registry.py`, `adapters/claude_code.py`, `adapters/chat.py`; commands `send`, `load`.

**Behavior:** two-file delivery (`.swallo/handoff/<id>.md` plus the fixed stub between `swallo:begin/end` markers); fence delimiter from `secrets.token_hex(16)`, regenerated if present in content; token budget with a heuristic estimator and `critical` items never trimmed; offer to add `.swallo/` to `.gitignore`; warn if swallo files are staged. All writes go through the path resolver. The IDE spike for Claude Code happens here (see section 14).

**Tests:** golden renders per adapter; fence-breakout fuzzing; marker-block idempotency (re-sending replaces only the block and preserves the rest of the file); budget behavior including the loud failure when critical items cannot fit; write confinement.

**Done when:** chat to Claude Code and chat to chat flows work end to end, and the spike result for Claude Code is recorded.

## 10. Step 6: Merge

**Files:** `merge/normalize.py`, `merge/dedupe.py`, `merge/conflicts.py`, `merge/resolve.py`; commands `merge`, `resolve`, `diff`; `send` accepting several IDs.

**Tests:** labelled fixtures including hard negatives (similar but compatible items); properties: merge is idempotent, order-invariant apart from conflict ordering, provenance is preserved, and nothing is ever auto-superseded; override-language fixtures surface as conflicts.

**Done when:** merge works in every delivery flow and conflict precision and recall on the fixture set are recorded with counts.

## 11. Step 7: MCP server and guards

**Files:** `server/mcp_server.py` (stdio, `[mcp]` extra), `server/guards.py`, `repo/gitstate.py`, `repo/staleness.py`; commands `staleness`, `drafts`, `breaker`; `doctor` MCP checks.

**Contents:** the five tools; dedupe; per-session token bucket; quotas and TTL; circuit breaker; stale policy with `--ack-stale`; project root registry; global-only `init` snippet with an absolute interpreter path; `doctor` checks for workspace-level configs and rogue data files. Per-project buckets are the fallback if an IDE exposes no stable session identifier.

**Verification during this step:** global config paths, session identifiers, workspace roots and terminal checks for Cursor, Claude Code and Antigravity (section 14).

**Tests:** MCP client integration tests for each tool and error code; the 500-call loop; breaker persistence across restarts and CLI unaffected; temp-repo staleness cases (unrelated commit, modified, renamed, deleted, rebase, acknowledgment expiry); unregistered-root refusal.

**Done when:** an agent in each verified IDE can save a draft and load an approved packet, and F18-F20 tests pass.

## 12. Step 8: Importers, benchmark harness, optional signing

- Importers one at a time (ChatGPT first), each with archive-limit and fuzz tests.
- `[sign]`: Ed25519 approvals via `cryptography`, imported lazily; passphrase stretched with `hashlib.scrypt` (proposal: n=2**15, r=8, p=1, with `maxmem` raised accordingly; measure timing on target machines; store salt and parameters in `meta`); known-vector tests; core-only CI job proves the core runs without it; verify the current `cryptography` API before coding.
- Phase 1 benchmark harness from `BENCHMARKS.md`.

## 13. Dependency order

```mermaid
flowchart LR
  S0[Step 0 Scaffold] --> S1[Step 1 Schema and hashing]
  S1 --> S2[Step 2 Store]
  S2 --> S3[Step 3 Safety spine]
  S3 --> S4[Step 4 CLI and help]
  S4 --> S5[Step 5 Delivery v0]
  S5 --> S6[Step 6 Merge]
  S6 --> S7[Step 7 MCP and guards]
  S7 --> S8[Step 8 Importers, bench, sign]
```

If several people contribute, Steps 1 and the sanitizer and path resolver from Step 3 can run in parallel, and redaction patterns can be built alongside Step 2.

## 14. IDE verification spikes

Run one short spike per IDE before building its adapter or MCP integration. Record results in `docs/security/IDE_VERIFICATION.md` using this table.

| Question | Claude Code | Cursor | Antigravity |
|---|---|---|---|
| Where does the user-level (global) MCP config live, and in what format? | | | |
| Does it accept an absolute interpreter path as the command? | | | |
| Which wins when a workspace-level config also exists? | | | |
| Does the agent load a referenced data file from the stub, without prompting? (test: ask a question answerable only from the data file) | | | |
| Does the MCP client expose workspace roots? | | | |
| Does it expose a stable session or connection identifier? | | | |
| Can an agent shell satisfy a terminal check (pseudo-terminal, `/dev/tty`)? | | | |
| How are MCP tool calls approved by default (prompt or auto)? | | | |
| Date and versions tested | | | |

If an IDE does not follow the pointer to a data file, record the fallback (manual paste or a different placement) and update ADR-006.

## 15. Guard tuning plan

- Starting values are the proposals in the TRD config table, marked experimental in 0.x.
- Collect from real prototype use: counts of `rate_limited`, `breaker_tripped`, `stale_blocked`, `stale_ack`, draft expirations, and each `breaker reset`.
- Review once there are enough real sessions to see a pattern. Signals of too-tight settings: frequent resets or acknowledgments in normal work. Signals of too-loose settings: floods or loops that were only stopped by quotas.
- A guard moves from experimental to default when typical use produces no unexplained blocks, its behavior is documented, and its Phase 1 guard tests pass.

## 16. v0.1 release gate

- [x] Steps 0-5 complete with all "done when" tests green on three operating systems (355 passed)
- [ ] F2, F3, F4, F5 and F10 tests pass (automated regression tests pass; independent review of F1-F5 pending independent reviewer)
- [x] Claude Code spike recorded; per-target behavior documented
- [x] Core-only CI job green (no extras installed; zero optional modules imported)
- [x] `swallo doctor` passes on a clean environment
- [x] Docs match behavior; changelog updated
- [ ] TestPyPI install and smoke test on all three operating systems (pending manual step; local wheel smoke test passed)
- [ ] Name availability confirmed (pending manual step; availability checked, pending upload)

## 17. Build risks and mitigations

| Risk | Mitigation |
|---|---|
| An IDE does not follow the pointer to the data file | Early spike; documented fallback; ADR-006 revisited |
| Canonicalization mistakes break approvals | Golden files, property tests, schema-major rule |
| Windows file semantics differ | Best-effort permissions, `posix_only` markers, CI on Windows from Step 0 |
| Redaction false positives frustrate users | Preview at review, deny-list and allow decisions, measured precision |
| Untuned guards obstruct legitimate use | Config-driven values, events, tuning plan, experimental label |
| `cryptography` wheels or API issues | Optional lazy import, core-only CI, known-vector tests |
| Scope creep into HTTP mode or benchmarks | Out-of-scope list in section 1 |
| Name availability or confusion | Check before first publish; check similar names |

## 18. First issues to open

1. Scaffold repo, CI matrix, core-only job.
2. `swallo version` and package metadata.
3. Canonical JSON with golden fixtures.
4. Pydantic models and generated JSON Schema.
5. Hash, packet ID and item ID derivation with property tests.
6. Store location helper and config loader.
7. SQLite connection, migrations, explicit transactions.
8. Object store with atomic writes and kill-during-write test.
9. Sanitizer with hidden-character fixtures.
10. Path resolver with symlink and traversal properties.
11. Hash-chained event log and `verify`.
12. Approval ledger and terminal confirmation.
13. Redaction engine, detectors and keyed placeholders.
14. Command registry and help system with completeness test.
15. `init`, `save`, `show`, `approve`, `log`.
