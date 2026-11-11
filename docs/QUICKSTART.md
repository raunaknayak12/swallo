# Swallo Quickstart Guide

Get up and running with Swallo in under 3 minutes.

Swallo provides a local-first, zero-network context handoff tool to pass debugging notes, architectural constraints, and task context between chat assistants (ChatGPT, Claude, Gemini) and agentic IDEs (Claude Code, Cursor, Antigravity) with human-in-the-loop review.

---

## 1. Installation

Install Swallo in your Python 3.11+ environment:

```bash
pip install swallo
```

To include optional features such as digital signatures (`[sign]`) or token counter approximation (`[tokens]`):

```bash
pip install "swallo[sign,tokens]"
```

Verify your installation:

```bash
swallo version
```

---

## 2. Initialize Swallo for Your Project

Navigate to your project root and run:

```bash
swallo init --project my-app
```

This registers your project root with Swallo and initializes your local store at `~/.local/share/swallo` (or `%LOCALAPPDATA%\swallo` on Windows), keeping all context data strictly outside your git tree.

---

## 3. Verify Health with Doctor

Run the built-in diagnostic suite:

```bash
swallo doctor
```

All checks should report `[OK]`.

---

## 4. IDE & Agent Integration (MCP)

Swallo exposes an official Model Context Protocol (MCP) server so your coding agents can read context packets directly.

### Claude Code
Add Swallo to Claude Code:

```bash
claude mcp add swallo -- swallo mcp
```

### Cursor
Add to your Cursor MCP settings (`Settings > Features > MCP`):
- **Name**: `swallo`
- **Type**: `command`
- **Command**: `swallo mcp`

### Antigravity IDE
Add to `.gemini/antigravity/mcp/swallo.json` (or your workspace MCP settings):

```json
{
  "name": "swallo",
  "command": "swallo",
  "args": ["mcp"]
}
```

---

## 5. Basic Workflow

### Step A: Capture Context from Chat
Paste a transcript or JSON export from your chat session:

```bash
swallo prompt "Working on session authentication"
```

### Step B: Inspect Context
View pending context packets:

```bash
swallo list
swallo show <packet_id>
```

### Step C: Approve Context for IDE Injection
Context handoffs require interactive human approval from a terminal:

```bash
swallo approve <packet_id> --target claude_code
```

### Step D: Deliver Context
Inject the approved context into your IDE:

```bash
swallo send <packet_id> --target claude_code
```

Swallo writes the full context into `.swallo/handoff/<packet_id>.md` and injects a pointer stub into your project's rules file (e.g. `CLAUDE.md`, `.cursorrules`, or `.agents/AGENTS.md`).

---

## 6. Security Guarantees

- **Zero-Network Invariant**: Core Swallo makes zero outgoing network calls.
- **Mandatory Human Approval**: Agents cannot approve context injection.
- **Redaction**: Passwords, API keys, and private keys are scrubbed before saving.
- **Trojan Source Protection**: Invisible characters and BiDi overrides are neutralized.
