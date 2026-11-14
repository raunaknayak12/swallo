# Swallo CLI Reference

Auto-generated reference documentation from `swallo <command> --help`.

## `swallo init`

```
usage: swallo init [-h] [--store STORE] [--force] [--project PROJECT] [--json]

Initialize swallo storage, local key, database, and project registry.

options:
  -h, --help            show this help message and exit
  --store STORE         Custom store directory override.
  --force, -f           Force re-initialization of an existing store.
  --project PROJECT, -p PROJECT
                        Project name to register for the current directory.
  --json                Output machine-readable JSON.
```

## `swallo prompt`

```
usage: swallo prompt [-h] [--target TARGET] [--project PROJECT] [--json]

Generate a structured handoff prompt to paste into a chat agent.

options:
  -h, --help         show this help message and exit
  --target TARGET    Target IDE/assistant (claude-code, cursor, antigravity,
                     chat).
  --project PROJECT  Target project name embedded into prompt schema (default:
                     default).
  --json             Output machine-readable JSON containing the prompt
                     string.
```

## `swallo save`

```
usage: swallo save [-h] [--store STORE] [--fail-closed] [--warn] [--json]
                   [file]

Validate, redact, and store a context packet from file or stdin.

positional arguments:
  file           Path to JSON packet file, or '-' to read from standard input.

options:
  -h, --help     show this help message and exit
  --store STORE  Store directory override.
  --fail-closed  Abort if any secret patterns or credentials are detected.
  --warn         Redact sensitive secrets with placeholders even if config
                 defaults to fail-closed.
  --json         Output machine-readable JSON.
```

## `swallo status`

```
usage: swallo status [-h] [--project PROJECT]
                     [--state {all,draft,approved,delivered}] [--store STORE]
                     [--json]

List stored packets and their current state (draft/approved/delivered).

options:
  -h, --help            show this help message and exit
  --project PROJECT     Filter by project name.
  --state {all,draft,approved,delivered}
                        Filter by approval/delivery state (default: all).
  --store STORE         Store directory override.
  --json                Output machine-readable JSON.
```

## `swallo list`

```
usage: swallo status [-h] [--project PROJECT]
                     [--state {all,draft,approved,delivered}] [--store STORE]
                     [--json]

List stored packets and their current state (draft/approved/delivered).

options:
  -h, --help            show this help message and exit
  --project PROJECT     Filter by project name.
  --state {all,draft,approved,delivered}
                        Filter by approval/delivery state (default: all).
  --store STORE         Store directory override.
  --json                Output machine-readable JSON.
```

## `swallo show`

```
usage: swallo show [-h] [--store STORE] [--json] packet_id

Display a context packet with a risk-first security summary.

positional arguments:
  packet_id      Packet identifier (e.g. pkt_...) or hash.

options:
  -h, --help     show this help message and exit
  --store STORE  Store directory override.
  --json         Output machine-readable JSON.
```

## `swallo approve`

```
usage: swallo approve [-h] [--target TARGET] [--ack-stale] [--repo REPO]
                      [--accept-untrusted] [--passphrase PASSPHRASE]
                      [--store STORE] [--json]
                      packet_id

Grant human approval for a packet to be delivered to a specific IDE target.

positional arguments:
  packet_id             Packet identifier (pkt_...) or hash to approve.

options:
  -h, --help            show this help message and exit
  --target TARGET, -t TARGET
                        Target IDE or agent adapter (default: claude-code).
  --ack-stale           Acknowledge repository staleness/drift and record
                        cryptographic acknowledgment.
  --repo REPO           Repository root path for staleness acknowledgment
                        (defaults to auto-detection).
  --accept-untrusted    Accept and approve an untrusted or externally imported
                        packet.
  --passphrase PASSPHRASE
                        Passphrase for Ed25519 digital signature of approval
                        (swallo[sign]).
  --store STORE         Store directory override.
  --json                Output machine-readable JSON.
```

## `swallo send`

```
usage: swallo send [-h] [--to TARGET] [--format {markdown}] [--store STORE]
                   [--project-root PROJECT_ROOT] [--budget BUDGET]
                   [--allow-unresolved] [--strict] [--dry-run] [--json]
                   packet_ids [packet_ids ...]

Render and deliver one or more context packets to a target IDE or chat.

positional arguments:
  packet_ids            One or more packet identifiers (pkt_...) or hashes.

options:
  -h, --help            show this help message and exit
  --to TARGET, -t TARGET
                        Target adapter: claude-code | chat (default: claude-
                        code).
  --format {markdown}   Delivery output format (default: markdown).
  --store STORE         Store directory override.
  --project-root PROJECT_ROOT
                        Project root directory override (defaults to current
                        directory).
  --budget BUDGET       Token budget limit (default: 4000).
  --allow-unresolved    Deliver with unresolved conflicts.
  --strict              Fail (exit 7) if the packet is stale.
  --dry-run             Show what would be written without writing any files.
  --json                Output machine-readable JSON.
```

## `swallo load`

```
usage: swallo load [-h] [--to TARGET] [--copied] [--store STORE]
                   [--budget BUDGET] [--json]
                   packet_id

Render an approved context packet to stdout for pasting into a chat.

positional arguments:
  packet_id             Packet identifier (pkt_...) or hash.

options:
  -h, --help            show this help message and exit
  --to TARGET, -t TARGET
                        Target chat or environment: chat | claude-code
                        (default: chat).
  --copied              Record a 'copied' event in the handoff ledger.
  --store STORE         Store directory override.
  --budget BUDGET       Token budget limit (default: 4000).
  --json                Output machine-readable JSON metadata alongside or
                        instead of raw text.
```

## `swallo diff`

```
usage: swallo diff [-h] [--json] [--store STORE] ID1 ID2

Compare two packets and show added / removed / common items.

positional arguments:
  ID1            First packet ID.
  ID2            Second packet ID.

options:
  -h, --help     show this help message and exit
  --json         Machine-readable JSON output.
  --store STORE  Store directory override.
```

## `swallo merge`

```
usage: swallo merge [-h] [--into TITLE] [--json] [--store STORE] ID [ID ...]

Merge two or more packets into a single draft packet.

positional arguments:
  ID             Packet IDs to merge (prefix match supported).

options:
  -h, --help     show this help message and exit
  --into TITLE   Title for the merged packet.
  --json         Machine-readable JSON output.
  --store STORE  Store directory override.
```

## `swallo resolve`

```
usage: swallo resolve [-h] --conflict CID (--keep ITEM_ID | --both) [--json]
                      [--store STORE]
                      MERGED_ID

Resolve a conflict in a merged packet.

positional arguments:
  MERGED_ID       ID of the merged packet.

options:
  -h, --help      show this help message and exit
  --conflict CID  Conflict ID to resolve.
  --keep ITEM_ID  Keep this item and discard the conflicting item(s).
  --both          Keep all conflicting items and drop the conflict marker.
  --json          Machine-readable JSON output.
  --store STORE   Store directory override.
```

## `swallo staleness`

```
usage: swallo staleness [-h] [--repo REPO] [--project PROJECT] [--store STORE]
                        [--json]
                        ID

Check whether the repository drifted since a packet was created.

positional arguments:
  ID                 Packet ID or hash to check.

options:
  -h, --help         show this help message and exit
  --repo REPO        Repository root path (defaults to auto-detection from
                     current directory).
  --project PROJECT  Project name filter.
  --store STORE      Store directory override.
  --json             Output machine-readable JSON.
```

## `swallo drafts`

```
usage: swallo drafts [-h] [--older-than DAYS] [--session SESSION]
                     [--project PROJECT] [--force] [--store STORE] [--json]
                     {list,purge}

Review or purge unapproved agent drafts.

positional arguments:
  {list,purge}       Action to perform: 'list' to view unapproved drafts,
                     'purge' to remove them.

options:
  -h, --help         show this help message and exit
  --older-than DAYS  Target drafts older than DAYS (e.g. 1, 7).
  --session SESSION  Target drafts from a specific MCP session ID.
  --project PROJECT  Target drafts from a specific project.
  --force, -f        Bypass interactive terminal confirmation when purging.
  --store STORE      Store directory override.
  --json             Output machine-readable JSON.
```

## `swallo breaker`

```
usage: swallo breaker [-h] [--session SESSION] [--force] [--store STORE]
                      [--json]
                      {status,reset}

Show or reset paused MCP sessions.

positional arguments:
  {status,reset}     Action to perform: 'status' to view sessions, 'reset' to
                     clear trips.

options:
  -h, --help         show this help message and exit
  --session SESSION  Target a specific session ID (defaults to all sessions).
  --force, -f        Bypass interactive confirmation prompt when resetting.
  --store STORE      Store directory override.
  --json             Output machine-readable JSON.
```

## `swallo import`

```
usage: swallo import [-h] [--list-sessions] [--select] [--session SESSION]
                     [--project PROJECT] [--store STORE] [--fail-closed]
                     [--warn] [--json]
                     {chatgpt,claude,gemini} archive

Import sessions from a ChatGPT, Claude, or Gemini data export archive.

positional arguments:
  {chatgpt,claude,gemini}
                        Vendor export format (chatgpt, claude, or gemini).
  archive               Path to archive (.zip) or JSON file.

options:
  -h, --help            show this help message and exit
  --list-sessions       List available conversation sessions in the archive
                        and exit.
  --select              Interactively select a session from the archive to
                        import.
  --session SESSION     Specific conversation session ID to import.
  --project PROJECT     Target project name for imported packets (default:
                        default).
  --store STORE         Store directory override.
  --fail-closed         Abort if any secret patterns or credentials are
                        detected.
  --warn                Redact sensitive secrets with placeholders even if
                        config defaults to fail-closed.
  --json                Output machine-readable JSON.
```

## `swallo mcp`

```
usage: swallo mcp [-h] [--http] [--port PORT] [--host HOST] [--token TOKEN]
                  [--store STORE]
                  [{serve}]

Run the swallo MCP server (stdio by default).

positional arguments:
  {serve}        Server action (default: serve).

options:
  -h, --help     show this help message and exit
  --http         Run loopback HTTP server instead of stdio.
  --port PORT    Port for HTTP loopback server (default: 8765).
  --host HOST    Bind address for HTTP server (default: 127.0.0.1).
  --token TOKEN  Authentication token required when running in HTTP mode.
  --store STORE  Store directory override.
```

## `swallo bench`

```
Usage: swallo bench <action> [options]

Actions:
  run     Execute benchmark suite and output results.json
  verify  Validate schema and cryptographic integrity of results.json

Run 'swallo bench <action> --help' for details on a specific action.
```

## `swallo doctor`

```
usage: swallo doctor [-h] [--store STORE] [--json]

Run security, configuration, and storage health diagnostics.

options:
  -h, --help     show this help message and exit
  --store STORE  Custom store directory override.
  --json         Output machine-readable JSON report.
```

## `swallo log`

```
usage: swallo log [-h] [--verify] [--limit LIMIT] [--store STORE] [--json]

Inspect and verify the tamper-evident audit event log.

options:
  -h, --help            show this help message and exit
  --verify              Traverse and cryptographically verify the integrity of
                        the HMAC hash chain.
  --limit LIMIT, -n LIMIT
                        Maximum number of log events to display (default: 25).
  --store STORE         Store directory override.
  --json                Output machine-readable JSON.
```

## `swallo version`

```
swallo 0.1.3
supported schema versions: 0.1
python: <python_version>
```
