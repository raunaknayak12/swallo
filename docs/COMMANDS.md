# Command Reference

**Status:** Draft v0.1. This is the intended behavior of the `swallo` CLI, derived from `CLI_AND_MCP_SPEC.md`. Example output is illustrative; exact wording may change during implementation.

## 1. Quick reference

| Command | What it does |
|---|---|
| `swallo init` | Create the local store, key and config; register the project |
| `swallo doctor` | Check environment, permissions, git-ignore and installed extras |
| `swallo prompt` | Print the structured prompt to give a chat model |
| `swallo save` | Save a pasted packet as a draft |
| `swallo import` | Import sessions from a ChatGPT, Gemini or Claude export |
| `swallo merge` | Merge 1 or more packets into one draft |
| `swallo resolve` | Resolve conflicts found by a merge |
| `swallo show` | Review a packet, its redactions and warnings |
| `swallo edit` | Edit a draft in `$EDITOR` (creates a new revision) |
| `swallo diff` | Compare two packets |
| `swallo list` | List packets in this project |
| `swallo status` | Show draft, approved and delivered state |
| `swallo approve` | Approve a packet for a target (terminal only) |
| `swallo send` | Render and deliver to an IDE or chat target |
| `swallo load` | Print a briefing to paste into a chat |
| `swallo log` | Show the handoff log; `--verify` checks integrity |
| `swallo staleness` | Check whether the repo changed since a packet was made |
| `swallo drafts` | Review or purge unapproved agent drafts |
| `swallo breaker` | Show or reset paused MCP sessions |
| `swallo bench` | Run or verify benchmarks |
| `swallo mcp` | Run the MCP server (stdio by default) |
| `swallo help` | Show help for the tool, a command or a topic |
| `swallo version` | Print version information |

**Targets** (for `--to` and `--target`): `claude-code`, `cursor`, `antigravity`, `agents-md`, `chat`. Antigravity support depends on verification of its current rules and MCP behavior.

**Global options:** `--project NAME`, `--store DIR`, `--json`, `--verbose`, `--no-color`, `-h/--help`, `--version`.

## 2. The help system

```
swallo help                 overview of all commands
swallo help <command>       usage, options, examples and exit codes for one command
swallo help <topic>         topics: flows | exit-codes | config | security
swallo help --all           every command with its options
swallo <command> --help     same as `swallo help <command>`
swallo --help, -h           same as `swallo help`
```

Behavior: works offline, never prints stored content, exits 0. An unknown command or topic exits with code 2 and suggests up to three close matches.

### 2.1 Example: `swallo help`

```
swallo 0.1.0 - reviewable handoff of AI conversation context between chat agents and IDEs

Usage:  swallo <command> [options]
        swallo help [command | topic]

Setup
  init        Create the local store, key and config for this project
  doctor      Check environment, permissions and git-ignore status

Capture
  prompt      Print the structured prompt to give a chat model
  save        Save a pasted packet as a draft
  import      Import sessions from a ChatGPT, Gemini or Claude export

Combine and review
  merge       Merge 1 or more packets into one draft
  resolve     Resolve conflicts found by merge
  show        Review a packet, its redactions and warnings
  edit        Edit a draft in $EDITOR (creates a new revision)
  diff        Compare two packets
  list        List packets in this project
  status      Show draft, approved and delivered state

Approve and deliver
  approve     Approve a packet for a target (terminal only)
  send        Render and deliver to an IDE or chat target
  load        Print a briefing to paste into a chat

Verify
  log         Show the handoff log; --verify checks its integrity
  staleness   Check whether the repo changed since a packet was made

Guards
  drafts      Review or purge unapproved agent drafts
  breaker     Show or reset paused MCP sessions

Evidence
  bench       Run or verify benchmarks

Servers
  mcp         Run the MCP server (stdio by default)

Help
  help        Show this screen, or help for a command or topic
  version     Print the version

Global options:
  --project NAME   --store DIR   --json   --verbose   --no-color   -h, --help   --version

Topics:  swallo help flows | exit-codes | config | security
```

### 2.2 Example: `swallo help send`

```
swallo send - render and deliver one or more packets to a target

Usage:
  swallo send <id> [<id> ...] --to <target> [options]

Description:
  Merges the packets if more than one is given, renders for the target, and writes
  the data file and stub. Requires approval for the target. Chat-derived content is
  delivered as a separate data file under .swallo/handoff/ with a fixed stub in the
  target's rules file.

Options:
  --to TARGET            claude-code | cursor | antigravity | agents-md | chat
  --allow-unresolved     deliver with conflicts clearly marked unresolved
  --strict               fail (exit 7) if the packet is stale
  --budget N             token budget override for this render
  --dry-run              show what would be written, write nothing

Examples:
  swallo send pkt_8c1f2a --to claude-code
  swallo send p1 p2 p3 --to cursor
  swallo send p1 p2 --to claude-code --allow-unresolved

Exit codes:  0 ok | 3 validation | 5 unresolved conflicts | 6 not approved | 7 stale (--strict)
```

## 3. Command synopses

```
swallo init [--project NAME] [--store DIR]
swallo doctor
swallo prompt [--target TARGET]
swallo save [--agent NAME] [--from-file FILE | --stdin]
swallo import chatgpt|gemini|claude ARCHIVE [--select]
swallo merge ID [ID ...] [--into NAME]
swallo resolve ID [--conflict CID (--keep ITEM | --both)]
swallo show ID [--rendered --target TARGET]
swallo edit ID
swallo diff ID_A ID_B
swallo list [--state draft|approved|delivered]
swallo status
swallo approve ID --target TARGET [--ack-stale] [--accept-untrusted]
swallo send ID [ID ...] --to TARGET [--allow-unresolved] [--strict] [--dry-run]
swallo load ID --to chat [--copied]
swallo log [--verify]
swallo staleness ID
swallo drafts list|purge [--older-than DAYS] [--session ID]
swallo breaker status|reset [--session ID]
swallo bench run [--phase N] [--seed S]
swallo bench verify RESULTS.json
swallo mcp serve [--http]
swallo help [COMMAND | TOPIC] [--all]
swallo version [--json]
```

## 4. Recipes

**Chat to IDE**
```
swallo prompt                       # paste the prompt into your chat; copy its reply
swallo save --stdin                 # paste the reply
swallo show pkt_8c1f2a              # review items and redactions
swallo approve pkt_8c1f2a --target claude-code
swallo send pkt_8c1f2a --to claude-code
swallo log
```

**Chat to chat**
```
swallo approve pkt_8c1f2a --target chat
swallo load pkt_8c1f2a --to chat    # paste the output into the next chat
```

**Merge several sessions into an IDE**
```
swallo import chatgpt conversations.zip --select
swallo merge p1 p2 p3 --into brainstorm-and-refactor
swallo resolve m1                   # settle each conflict
swallo approve m1 --target cursor
swallo send m1 --to cursor
```

**IDE to IDE**
```
# agent A calls save_context over MCP (creates a draft)
swallo show pkt_77aa
swallo approve pkt_77aa --target claude-code
# agent B calls load_context, or: swallo send pkt_77aa --to claude-code
swallo staleness pkt_77aa
```

**An agent's load was blocked as stale**
```
# the agent received stale_context_blocked
swallo staleness pkt_8c1f2a                         # see which files drifted
swallo approve pkt_8c1f2a --target claude-code --ack-stale
```
The acknowledgment expires if HEAD or the drifted files change again.

**An MCP session was paused after repeated blocked saves**
```
swallo breaker status
swallo show pkt_77aa                                # review what the agent was trying to save
swallo breaker reset --session SESSION_ID
```

**Clear a flood of unapproved agent drafts**
```
swallo drafts list
swallo drafts purge --older-than 1
```

**Approve an imported (untrusted) packet**
```
swallo show pkt_91be                                # read the risk summary first
swallo approve pkt_91be --target cursor --accept-untrusted
```

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error |
| 2 | Usage error (including unknown command or topic) |
| 3 | Validation failure (schema or limits) |
| 4 | Redaction blocked the operation (fail closed) |
| 5 | Unresolved conflicts |
| 6 | Not approved |
| 7 | Stale packet with `--strict` |
| 8 | Integrity failure (log chain or store check) |
