# Product Requirements Document (PRD)

**Product:** swallo | **Status:** Draft v0.1 | **Date:** 2026-10-25

## 1. Summary

swallo is an open-source Python package (PyPI) that moves context between AI agents: chat apps (ChatGPT, Claude, Gemini) and IDE agents (Claude Code, Cursor, Antigravity). Context is carried as a validated, reviewable JSON packet, redacted before storage, mergeable across 2+ sessions, and delivered in the format each target expects.

**Pitch:** portable, reviewable handoff between any chat agent and any IDE, with reproducible evidence that it works.

## 2. Problem

People think through problems in one chat, want a second opinion from another model, or want an IDE agent to start building from the discussion. Today they copy-paste long transcripts or write summaries by hand. Existing memory tools appear to focus on coding agents and ambient memory (a limited sample of tools was surveyed; verify before claiming gaps). Gaps this product targets:

1. Getting a discussion out of chat apps and into an IDE agent.
2. Merging several sessions with provenance and explicit conflict resolution.
3. Evidence that a handoff actually helps the next agent.
4. A safe default: secrets redacted, imported text treated as untrusted, a human review before delivery.

## 3. Goals and non-goals

### Goals
- G1. Handoff for chat to IDE, chat to chat, and IDE to IDE, each accepting 1..N source sessions.
- G2. A canonical JSON packet that is validated, versioned, diffable and mergeable.
- G3. Local-first operation: no account, no Docker, no LLM key in the core.
- G4. Secure defaults (see `Security.md`).
- G5. Visible workflow: users can see what was saved, approved and delivered.
- G6. Claims backed by pre-registered, reproducible benchmarks (`BENCHMARKS.md`).

### Non-goals
- Not an ambient memory store that records everything silently.
- Not a content-moderation or "AI safety" layer.
- No LLM calls in the core pipeline (an optional plugin interface may exist later).
- No cloud sync in v1.
- No browser extension in v1 (JavaScript is outside the pure-Python stack; may live in a separate repository later).
- No claim that the receiving agent understood the packet.

## 4. Personas

| Persona | Need | Primary flow |
|---|---|---|
| **Solo builder** | Turn a ChatGPT/Claude design discussion into a working start in Claude Code or Cursor | Chat to IDE |
| **Model comparer** | Ask the same question across models without re-explaining | Chat to chat |
| **Multi-session developer** | Combine Monday's brainstorm and Wednesday's refactor chats into one consistent brief, with disagreements surfaced | Merge, then any target |
| **Cautious/enterprise-minded user** | Know exactly what leaves the machine and that secrets are stripped | All flows, review and log |

## 5. User stories

| ID | Story | Priority |
|---|---|---|
| US-1 | As a builder, I save a chat discussion and load it into my IDE agent so it starts with the context | P0 |
| US-2 | I merge two or more sessions and resolve conflicts myself instead of the tool silently choosing | P0 |
| US-3 | I preview exactly what will be sent, including what was redacted, before approving | P0 |
| US-4 | I see a log of what was saved, approved, written or served | P0 |
| US-5 | I import past conversations from a vendor data export and pick sessions to merge | P1 |
| US-6 | I get a paste-ready briefing for another chat model | P0 |
| US-7 | I am warned when the repo has changed since a packet was made | P1 |
| US-8 | I can run the benchmark suite myself and submit results | P1 |
| US-9 | I can expose the tool to chat apps that support remote connectors, opt-in | P2 |
| US-10 | I am protected from runaway or manipulated agents: they cannot flood drafts, retry around blocks, or load stale context without my decision | P0 |

## 6. Functional requirements

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| FR-1 | Capture via structured-paste prompt (`swallo prompt`, `swallo save`) | P0 | A packet validates against the schema for pasted output from any chat; invalid output gives field-level errors |
| FR-2 | Capture from IDE agents via MCP `save_context` | P0 | Agent-written packet is validated, redacted and stored as an unapproved draft |
| FR-3 | Import ChatGPT export, Gemini Takeout, Claude export | P1 | Import lists sessions and lets the user select; hostile archives are rejected safely |
| FR-4 | Fail-closed redaction before any write | P0 | Seeded and real-corpus secrets are not present in store, log or errors (measured, with stated recall) |
| FR-5 | Merge 1..N packets with dedup, provenance, conflict detection | P0 | Conflicts block delivery until resolved or are delivered explicitly marked unresolved |
| FR-6 | Review preview and local approval bound to packet hash | P0 | Editing after approval requires re-approval; imported packets start unapproved |
| FR-7 | Delivery adapters: Claude Code, Cursor, Antigravity, generic AGENTS.md, chat briefing | P0 (Claude Code, Cursor, briefing), P1 (others) | Output matches each target's expected structure; two-file delivery by default |
| FR-8 | MCP server (stdio) with `save_context`, `load_context`, `merge_contexts`, `diff`, `list_contexts` | P0 | A test MCP client can call each tool; `load_context` serves approved packets only |
| FR-9 | Token-budgeted rendering with `critical` items never trimmed | P0 | Rendering fails loudly if critical items cannot fit; trimmed items are listed |
| FR-10 | Handoff log, hash-chained, with `swallo log --verify` | P0 | Verification detects edited or removed entries |
| FR-11 | Staleness warning from git commit and file hashes | P1 | Warning names exactly the drifted files; no warning when unchanged |
| FR-12 | `swallo bench run` producing `results.json` with an environment manifest | P1 | Another machine can reproduce and submit results |
| FR-13 | Optional remote MCP (HTTP) mode | P2 | Off by default; token auth; documented data flow |
| FR-14 | MCP guard layer: dedupe, per-session rate limit, quotas, TTL for unapproved drafts, circuit breaker on repeated blocked saves | P0 | A 500-call loop does not grow the store beyond quota; CLI keeps working; thresholds configurable |
| FR-15 | Deterministic stale policy: MCP loads blocked on critical drift unless a human acknowledgment bound to hash, HEAD and drifted-file hashes exists | P0 | Unrelated commits do not block; acknowledgment expires on change |
| FR-16 | Global-only MCP setup, project root registry, `doctor` checks for workspace configs and rogue data files | P0 | Loads from unregistered roots are refused; `doctor` reports poisoned configs |
| FR-17 | Optional passphrase-signed approvals (`[sign]` extra) | P2 | Approvals verify against a stored public key; re-init requires the passphrase |

## 7. Non-functional requirements

- **Privacy:** no network access in the core; data stays in a local store with restrictive permissions.
- **Reliability:** no partial writes; safe under concurrent saves from multiple agents.
- **Performance:** save and load of a typical packet should feel instant. Concrete targets are set from Phase 1 baselines (proposal: under 1 second for a typical packet on a laptop).
- **Portability:** Linux, macOS, Windows; Python 3.11+ (decided).
- **Footprint:** minimal runtime dependencies (Pydantic only in the core; see TRD).
- **Transparency:** every claim in docs maps to a test or is marked as design intent.

## 8. Success metrics

Product metrics (measured, never assumed): time to first successful handoff on a clean machine; share of handoffs approved without edits; redaction recall/precision on the labelled corpus; conflict-detection precision/recall; downstream task success versus baselines (`BENCHMARKS.md` Phase 3); install and issue counts after release.

No target values are stated until baselines exist.

## 9. Release scope

| Release | Contents |
|---|---|
| **v0.1** | Schema and hashing, SQLite store and object store, safety spine (redaction baseline, ledger, log), structured-paste capture, CLI with help, Claude Code and chat-briefing delivery. No MCP server yet |
| **v0.2** | Merge and conflicts in all flows, stdio MCP server with guards, staleness, global-only MCP setup and `doctor` checks, Cursor adapter after its IDE spike |
| **v0.3** | Importers (ChatGPT first), Antigravity and AGENTS.md adapters after their spikes, Phase 1 and 2 benchmark harnesses, optional `[sign]`, optional gitleaks/Presidio integrations |
| **Later** | Remote HTTP mode (opt-in), conflict-detector plugins, separate-repo browser extension |

## 10. Competitive positioning

Related tools surveyed in a limited sample: Open Memory Protocol, ContextStream, threadctx, baton-mcp, OpenMemory. They appear to emphasize persistent or ambient memory and coding agents. This product differs by design: explicit user-triggered handoff, chat-app capture, merge with conflict resolution, a local approval step, and outcome-based benchmarks. Validate each comparison against current READMEs before publishing it.

## 11. Risks and assumptions

- Chat apps do not expose conversations to outside servers on their own; capture depends on structured paste, vendor exports or connectors, all of which have limits.
- Model-written summaries can drop or distort content; the packet records `capture_method` so users know the fidelity.
- Rules-file behavior differs per IDE and may change.
- Benchmark outcomes may not favor the tool; the plan is designed so any outcome is publishable.
- Phase 3 evaluation costs real model usage.
- An agent with unrestricted shell or file access can bypass local approval; baseline controls cannot fully prevent this, and containment depends on the IDE's sandbox and permission prompts.
- Guard thresholds are untuned prototype defaults (experimental in 0.x); they may obstruct legitimate use or miss abuse until tuned from real usage.

## 12. Open questions

1. Confirm `swallo` is available on PyPI.
2. License is MIT (decided); confirm no dependency conflicts with it.
3. Default for stored transcripts: redacted only (recommended) versus optional raw.
4. Whether any auto-approval policy is ever allowed (default: never).
5. Which conflict-detector plugin interface to offer for users who want model assistance.
