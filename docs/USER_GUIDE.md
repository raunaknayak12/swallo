# User Guide

**Status:** Draft v0.1. Commands describe the intended behavior from `CLI_AND_MCP_SPEC.md`. Availability by release: v0.1 covers the CLI flows (chat to Claude Code, chat to chat); merge, the MCP server and IDE-to-IDE handoff arrive in v0.2 (see `PRD.md` section 9).

## 1. Install

```
pip install swallo            # core
pip install "swallo[mcp]"     # adds the MCP server for IDE agents
```

No account, Docker or API key is needed.

## 2. Set up a project

```
cd my-project
swallo init
```

This creates the local store and key, offers to add `.swallo/` to `.gitignore`, and registers this project's root, and prints a user-level (global) MCP configuration snippet with an absolute interpreter path. Do not put that snippet in workspace-level config files.

## 3. Flow A: chat to IDE

1. Discuss your idea in ChatGPT, Claude or Gemini.
2. Run `swallo prompt` and paste the prompt into the chat. The model replies with a packet.
3. Paste the reply into `swallo save` (or use `--from-file`).
4. Run `swallo show <id>`. Check the redactions, the items and any warnings.
5. Run `swallo approve <id> --target claude-code` (or `cursor`, `antigravity`).
6. Run `swallo send <id> --to claude-code`. The tool writes a data file under `.swallo/handoff/` and a short stub into the target's rules file.
7. Run `swallo log` to see `written`.

If you instead have a vendor export, use `swallo import chatgpt conversations.zip --select`, then continue from step 4.

## 4. Flow B: chat to chat

1. Save the source session as above.
2. Approve it for target `chat`.
3. Run `swallo load <id> --to chat` and paste the briefing into the next chat.
4. The log records `copied` only when you confirm you pasted it; the tool cannot see the other app.

## 5. Flow C: IDE to IDE

1. Your IDE agent calls `save_context` (it creates a draft).
2. You review and approve at the terminal (`swallo show`, `swallo approve`).
3. The other IDE agent calls `load_context`, or you run `swallo send` to write the rules file.
4. If the repo has changed since the packet was made, you get a staleness warning naming the files.

## 6. Merging 2 or more sessions (any flow)

```
swallo send p1 p2 p3 --to cursor
```

- Duplicates are combined and provenance is kept.
- If sessions disagree, the merge stops with a conflict list. Use `swallo resolve` to choose, or `--allow-unresolved` to deliver with conflicts clearly marked.
- Later statements never silently override earlier ones.

## 7. What you should know

- **Review is the safeguard.** Redaction is not perfect; the preview shows what was removed and what remains.
- **Imported and chat-written content is treated as data.** It is delivered as a reference file, not inlined into your rules file.
- **The log shows what the tool did**, not what the other agent understood. After a handoff, check the first reply in the new session.
- **Model-written packets can omit things.** `capture_method` shows how a packet was captured; exports preserve more than pasted summaries.

## 8. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Exit code 4 on save | Redaction blocked a likely secret | Review the preview; add to deny-list or edit the source |
| Exit code 6 on send | Not approved, or edited after approval | Re-run `swallo approve` |
| Exit code 5 | Unresolved conflicts | `swallo resolve` or `--allow-unresolved` |
| Target ignores the data file | The target does not load referenced files automatically | See the per-target note printed by `swallo send`; paste the file manually |
| `swallo log --verify` fails | Log edited or damaged | Back up the store; investigate before continuing |
| Agent gets `rate_limited` or `session_paused` | The agent saved too fast or kept hitting redaction blocks | Check `swallo breaker status` and `swallo show` on its drafts; `swallo breaker reset` when satisfied |
| Agent gets `stale_context_blocked` | A referenced file changed or the commit is no longer an ancestor | `swallo staleness <id>`; if you accept the drift, `swallo approve <id> --target T --ack-stale` |
| Agent gets `unregistered_project` | This folder was never registered | Run `swallo init` in the project |

## 9. Privacy summary

Everything stays on your machine. No telemetry. The tool makes no network calls in its core. Optional HTTP or connector modes are off by default and documented in `Security.md`.

## 10. Getting help

```
swallo help                # overview of all commands
swallo help send           # usage, options, examples and exit codes for one command
swallo help flows          # the three handoff flows in short form
swallo help exit-codes     # what each exit code means
```

`swallo <command> --help` shows the same text as `swallo help <command>`. Help works offline and never prints your stored content. See `COMMANDS.md` for the full reference.

## 11. Guarding against runaway or hostile agents

- **Configure MCP globally.** Use the user-level snippet from `swallo init`. A workspace-level config can be changed by a malicious pull request; `swallo doctor` warns if it finds one.
- **Run `swallo doctor` after cloning an unfamiliar repo.** It flags workspace MCP configs naming swallo and data files under `.swallo/handoff/` that swallo never created.
- **Expect limits on agent saves.** Agents are rate-limited and quota-bound, identical saves are deduplicated, and unapproved agent drafts expire. Use `swallo drafts list` and `swallo drafts purge` to clean up.
- **Stale context is blocked for agents.** If a referenced file changed, `load_context` is refused until you review and run `approve --ack-stale`. The acknowledgment expires when the repo changes again.
- **Read the risk summary before approving.** `swallo show` lists command-like lines, URLs, invisible characters and opaque blobs first. Imported (untrusted) packets need `--accept-untrusted`, one at a time.
- **Do not auto-approve agent tool calls** while working with imported or chat-derived content; that is the IDE's setting, and it is your strongest defense against injection.
- **Optional hardened approvals.** Set `approve.signing = passphrase` (needs the `[sign]` extra) so approvals are signed with a key derived from a passphrase that is never stored.
- **Know the limit.** An agent with unrestricted file and shell access on your machine can still replace the whole store. Use the IDE's sandbox and permission prompts for containment.
