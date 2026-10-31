# CLI and MCP Specification

**Status:** Draft v0.1 | Related: `TRD.md`, `PACKET_SCHEMA.md`, `Security.md`

## 1. CLI overview

Entry point: `swallo` (decided). Python module form: `python -m swallo`. Common flags: `--project <name>`, `--store <dir>`, `--json` (machine-readable output), `--verbose`, `--no-color`.

| Command | Purpose | Key behavior |
|---|---|---|
| `swallo help [command\|topic]` | Show the command overview, or help for one command or topic | Offline; prints no stored content; `--all` expands every command's options; unknown names exit 2 with close-match suggestions |
| `swallo version` | Print version, supported schema versions and Python version | `--json` for scripts |
| `swallo init` | Create store, local key, config; register the project | Sets permissions; offers `.gitignore` entry; registers the project root; prints a **global** (user-level) MCP setup snippet with an absolute interpreter path; `--force` re-init requires a terminal and is logged |
| `swallo prompt [--target ...]` | Print/copy the structured-paste prompt that asks a chat model to output a packet | Prompt embeds the schema summary; no network |
| `swallo save [--agent NAME] [--from-file F] [--stdin]` | Capture a pasted packet | Limits, parse, redact, validate; stores a draft; prints redaction summary |
| `swallo import <chatgpt\|gemini\|claude> <archive>` | Import sessions from a vendor export | Streams safely; lists sessions; `--select` chooses; produces draft packets |
| `swallo merge <id...> [--into NAME]` | Merge 1..N packets | Produces a draft with conflicts listed |
| `swallo resolve <id> [--conflict ID --keep ITEM \| --both]` | Resolve conflicts | Creates a new revision with a new hash |
| `swallo show <id> [--rendered --target T]` | Review a packet and its redactions | Sanitized output; highlights command-like text and unresolved conflicts first |
| `swallo edit <id>` | Edit a draft in `$EDITOR` | Result becomes a new revision, tier T0 for edited items |
| `swallo approve <id> --target T [--ack-stale] [--accept-untrusted]` | Approve for delivery | Requires a terminal (best effort); binds to hash and target; `--ack-stale` records an expiring acknowledgment for drifted context; `--accept-untrusted` is required per T3 packet; no bulk approval |
| `swallo send <id...> --to T` | Merge if needed, render and deliver | Fails if unapproved, stale (with `--strict`), or conflicts unresolved without `--allow-unresolved` |
| `swallo load <id> --to T` | Render to stdout (for pasting into chats) | Records `copied` only when `--copied` is confirmed by the user |
| `swallo diff <a> <b>` | Compare two packets | Item-level; shows provenance |
| `swallo list`, `swallo status` | Packets and their state (draft/approved/delivered) | |
| `swallo log [--verify]` | Show the event log; verify hash chain | Exit code 8 on failure |
| `swallo staleness <id>` | Compare packet repo_state to HEAD | Names drifted files |
| `swallo drafts list\|purge [--older-than DAYS] [--session ID]` | Review or purge unapproved agent drafts | CLI only; never touches approved or referenced packets |
| `swallo breaker status\|reset [--session ID]` | Show or reset paused MCP sessions | Reset requires a terminal; logged |
| `swallo bench run \| verify <results.json>` | Run the benchmark suite; verify a submitted result | See `BENCHMARKS.md` |
| `swallo doctor` | Check environment, permissions, git ignore, extras, MCP setup | Reports permission checks (best effort on Windows) and store location; warns about workspace-level MCP configs naming `swallo`, unregistered roots, and `.swallo/handoff/` files with no ledger record; prints no content |
| `swallo mcp serve [--http]` | Start the MCP server | stdio default; HTTP requires explicit flag, token, loopback bind |

### 1.1 Help system

- `swallo help` shows the grouped command overview; `swallo help <command>` shows usage, options, examples and exit codes for one command; `swallo <command> --help` is equivalent.
- Topics: `flows`, `exit-codes`, `config`, `security`.
- Help text lives in one module (`help.py`) so the CLI, the docs and tests share a single source. A test asserts every registered command has help text, at least one example and listed exit codes.
- Help is offline and never prints stored content. An unknown command or topic exits with code 2 and suggests up to three close matches.
- Valid targets: `claude-code`, `cursor`, `antigravity`, `agents-md`, `chat` (Antigravity pending verification).
- Full example output: `COMMANDS.md`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error |
| 2 | Usage error |
| 3 | Validation failure (schema or limits) |
| 4 | Redaction blocked the operation (fail closed) |
| 5 | Unresolved conflicts |
| 6 | Not approved |
| 7 | Stale packet with `--strict` |
| 8 | Integrity failure (log chain or store check) |

## 2. Event types written to the log

`saved`, `merged`, `resolved`, `approved`, `written`, `served`, `copied`, `blocked`. Metadata only: time, packet hash, target, type, short detail. Never content. Wording is deliberate: the tool never claims an agent "received" or "understood" a packet.

## 3. MCP server

Transport: stdio by default. Tool descriptions are static and contain no user content. All arguments are untrusted input.

### Tools

| Tool | Input | Output | Notes |
|---|---|---|---|
| `save_context` | `packet` (object matching schema) or `digest` fields; `agent`; `project` | `{id, hash, redactions, warnings}` | Stores an **unapproved draft**, tier T1; limits, redaction, validation apply |
| `load_context` | `id` or `latest`; `target`; `project` | Rendered content or packet JSON | **Approved packets only**; records `served`; project-scoped; may include staleness warnings |
| `merge_contexts` | `ids[]`; `into` | `{id, hash, conflicts[]}` | Produces an unapproved draft; conflicts listed |
| `diff` | `a`, `b` | Item-level differences with provenance | Read-only |
| `list_contexts` | `project`; `state` filter | List of ids, state, tier, created_at | No content |

### Deliberately absent
- No `approve` tool (SR-06). Human approval happens at a TTY.
- No tool that reads arbitrary files or paths.
- No tool that returns raw transcripts.

### Errors
Structured error with a code (`validation`, `redaction_blocked`, `session_paused`, `rate_limited`, `not_approved`, `stale_context_blocked`, `conflicts_unresolved`, `unregistered_project`, `not_found`, `limits`), a message naming the problem without echoing content.

### Guard behavior

| Situation | Response |
|---|---|
| Likely secret in a save | `redaction_blocked` with a count only; pattern detail is shown in the CLI, not to the agent |
| Repeated blocked saves from one session | `session_paused` after the breaker threshold; CLI unaffected; `swallo breaker reset` clears it |
| Too many saves | `rate_limited` with a retry time; identical payloads return the existing draft without consuming budget |
| Unapproved packet | `not_approved` |
| Critical drift (modified, deleted, renamed referenced file, or commit not an ancestor of HEAD) | `stale_context_blocked` with drifted file names, unless a valid acknowledgment exists |
| Project root not registered | `unregistered_project` |

`load_context` output is wrapped in a CSPRNG-generated fence with a leading notice that the content is data, not instructions, and each item shows its provenance tier.

### Setup snippets (verify per target)
`swallo init` prints a **user-level (global)** configuration entry for each supported IDE, using an absolute interpreter path such as `/abs/path/python -m swallo mcp serve` rather than a bare command resolved through `PATH`. Do not place it in workspace-level config files, which a malicious pull request can change; `swallo doctor` warns if it finds one. Exact file locations and formats differ per IDE and version; verify against each IDE's current documentation.

## 4. HTTP mode (optional, off by default)

`swallo mcp serve --http` binds `127.0.0.1`, requires a per-install bearer token, validates Host and Origin against an allow-list, and refuses a non-loopback bind without `--allow-remote-bind`. A tunnel or relay for chat-app connectors is the user's explicit choice and is documented as having privacy implications.
