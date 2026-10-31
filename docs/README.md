# swallo: Documentation Pack

**Status:** Draft v0.1, 2026-10-25. Design stage: no code exists yet, and no benchmark has been run.
**Name:** `swallo` (distribution, import name and CLI command). **License:** MIT. **Minimum Python:** 3.11. Previously `stowbit`, and before that `ctx-handoff`. Confirm the name is available on PyPI, and check similar names (for example `swallow`), before the first publish (see `docs/PACKAGING_AND_RELEASE.md`).

## What this project is

An open-source, pure-Python package, distributed on PyPI, that moves the context of one or more AI conversations to another agent. Sources and targets include chat apps (ChatGPT, Claude, Gemini) and IDE agents (Claude Code, Cursor, Antigravity). Context travels as a validated, reviewable JSON "context packet". Merging 2+ sessions works in every flow.

One-line pitch: **portable, reviewable handoff between any chat agent and any IDE, with reproducible evidence that it works.**

## Contents

| File | Purpose |
|---|---|
| `docs/PRD.md` | Product requirements: users, goals, features, scope by release |
| `docs/TRD.md` | Technical requirements: stack, modules, storage, pipeline, testing |
| `docs/Security.md` | Security design, threat model, findings F1-F21 and mitigations |
| `docs/Paper.md` | In-depth architecture paper: the reasoning behind the design |
| `docs/PACKET_SCHEMA.md` | The context packet format (the core contract) |
| `docs/CLI_AND_MCP_SPEC.md` | CLI commands and MCP tools, with behavior and exit codes |
| `docs/COMMANDS.md` | Command reference, including the `swallo help` screen and recipes |
| `docs/USER_GUIDE.md` | How users install and use the tool |
| `docs/BENCHMARKS.md` | Evaluation plan and claims policy |
| `docs/ROADMAP.md` | Milestones, exit criteria, backlog |
| `docs/IMPLEMENTATION_PLAN.md` | Step-by-step build plan: interfaces, tests, exit criteria, IDE spikes, guard tuning |
| `docs/PACKAGING_AND_RELEASE.md` | PyPI packaging, CI, release checklist |
| `docs/DECISIONS.md` | Architecture decision records (ADRs) |
| `docs/security/FINDINGS_REGISTER.md` | Live register for threat-model findings |
| `docs/templates/PREREGISTRATION.md` | Benchmark pre-registration template |
| `docs/templates/ANNOTATION_GUIDE.md` | Guide for human-labelled ground truth |
| `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` | Standard repository files |

## Suggested reading order

1. `PRD.md` (what and why), 2. `Paper.md` (how it fits together), 3. `TRD.md` and `PACKET_SCHEMA.md` (build details), 4. `Security.md`, 5. `BENCHMARKS.md`, 6. `ROADMAP.md`, 7. `IMPLEMENTATION_PLAN.md` (what to build first, step by step).

## Conventions

- MUST / SHOULD / MAY follow their usual requirement meanings.
- "Proposal" marks a value or choice that is a starting point, to be confirmed by measurement or review.
- "Verify" marks a statement about an external product, library or format that was not confirmed against official documentation. Confirm each before building on it.

## Assumptions to verify before building

1. That the name `swallo` is available on PyPI, and that no similar existing name creates confusion.
2. The current API of the official Python MCP SDK, and how each target IDE loads MCP servers.
3. How each target (Claude Code, Cursor, Antigravity) discovers and prioritizes rules files, and whether it follows a pointer to a separate data file.
4. Whether `tiktoken` needs network access on first use (this tool's default token estimator avoids it).
5. Current export formats of ChatGPT, Claude and Gemini (Takeout), and current connector support per plan.
6. PyPI trusted-publishing setup steps.
7. Competitor capabilities (Open Memory Protocol, ContextStream, threadctx, baton-mcp, OpenMemory) from their current READMEs. Only a limited sample was surveyed during design.
8. Whether each IDE supports user-level (global) MCP configuration with absolute interpreter paths, exposes a stable MCP session identifier and workspace roots, and whether agent shells can satisfy a terminal check through a pseudo-terminal.
