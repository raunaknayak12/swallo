# Swallo System Architecture

This document describes the architectural layout, core subsystems, component interactions, and security invariants of **Swallo**.

---

## 1. Architectural Overview

Swallo is a zero-network, local-first context transfer bridge designed to exchange structured context packets between AI chat assistants (e.g. ChatGPT, Claude, Gemini) and local development IDE agents (e.g. Claude Code, Cursor, Antigravity) with deterministic sanitization, redaction, and cryptographic auditability.

```
       Chat Agent / Export Archive / CLI Prompt
                          │
                          ▼
            [ Capture & Importer Layer ]
       (JSON schemas, ChatGPT/Claude/Gemini)
                          │
                          ▼
             [ Redaction & Decode Engine ]
   (Regex patterns, Base64/Hex/Rot13 scan, fail-closed)
                          │
                          ▼
         [ Canonical Serialization & Hashing ]
       (Deterministic JSON, SHA-256, packet ID)
                          │
                          ▼
            [ Local SQLite & Object Store ]
    (WAL mode, PRAGMA foreign_keys, event hash chain)
                          │
                          ▼
            [ Human Approval Gate (TTY) ]
    (Interactive confirmation, HMAC ledger, Ed25519)
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
 [ File Delivery Engine ]         [ FastMCP Server ]
(Two-file pattern, nonce fences) (Strict approval gates, rate limit, breaker)
          │                               │
          ▼                               ▼
 IDE Workspace (CLAUDE.md, etc.)   IDE Agent Tools (stdio)
```

---

## 2. Core Subsystems

### 2.1 Capture & Importers (`swallo.capture`)
- Parses structured conversation transcripts, chat dumps, and manual CLI prompts.
- Vendor adapters for ChatGPT (`conversations.json`), Claude data exports, and Gemini Takeout.
- Extracts goal, decisions, constraints, questions, and artifact references into standard Pydantic models.
- Preserves full provenance (`session_id`, `capture_method`, timestamps).

### 2.2 Redaction Engine (`swallo.redact`)
- Multi-layer regex and heuristic detector for credentials (AWS, GitHub, Slack, Stripe, JWT, private keys, database URLs, generic API tokens).
- Variant decoding (`swallo.redact.decode`): scans Base64, Hex, URL-encoding, Rot13, and reversed tokens.
- Entropy detection (`OpaqueBlobDetector`): flags high-entropy strings exceeding length and entropy thresholds.
- Enforces `--fail-closed` policy by default (blocking save on detected secrets) or `--warn` (substituting deterministic redaction placeholders).

### 2.3 Canonical Schema & Deterministic Hashing (`swallo.schema`)
- Canonical JSON serialization per RFC 8785 rules (`canonicalize`): sorted keys, compact separators, UTF-8 encoded without unescaped controls.
- Content-addressed hashing (`hashed_form` and `packet_hash`): SHA-256 calculated over canonical representations, deriving deterministic packet IDs (`pkt_<12-hex>`).

### 2.4 Local Secure Store & Event Log (`swallo.store`)
- SQLite database (`swallo.db`) in WAL mode with autocommit (`isolation_level=None`) and immediate transactions.
- 32-byte cryptographically secure local key (`key`) with `0600` file permissions.
- Content-addressed object store (`objects/`) storing raw canonical bodies.
- Append-only cryptographic audit event log (`events` table): SHA-256 HMAC hash chain where each event includes the previous event's MAC.
- Cryptographic approval ledger (`approvals` table): records per-target human approvals keyed with HMAC.
- Optional passphrase-derived digital signing (`swallo.store.signing`): Ed25519 signatures derived via `scrypt` without storing private keys on disk.

### 2.5 Target Adapters & Nonce Fences (`swallo.adapters`, `swallo.render`)
- Two-file delivery pattern:
  1. Data briefing file: `.swallo/handoff/<packet-id>.md` wrapped in CSPRNG nonce fences.
  2. Workspace instruction stub: `.cursorrules`, `CLAUDE.md`, or `AGENTS.md` referencing the data file.
- Preserves existing developer instructions by updating bounded comment marker blocks (`<!-- swallo:begin -->` ... `<!-- swallo:end -->`).
- Terminal escape and Trojan Source bidi sanitization (`swallo.render.sanitize`): strips ANSI escape sequences, Unicode direction overrides (`\u202e`, `\u2066`), and zero-width characters.

### 2.6 Git Repository State & Staleness Tracking (`swallo.repo`)
- Captures commit hash, dirty status, and blob hashes of referenced workspace files (`RepoState`).
- Staleness detector (`swallo.repo.staleness`): verifies commit ancestry (detecting rebases or branch switches) and referenced file drift.
- Cryptographic staleness acknowledgments (`stale_acks` table): stores HMAC-authenticated drift acknowledgments with expiring TTLs.

### 2.7 FastMCP Server (`swallo.server`)
- Stdio-based Model Context Protocol (MCP) server for direct agent integration.
- Exactly 7 safe tools registered: `save_context`, `load_context`, `get_context`, `verify_context`, `merge_contexts`, `diff`, `list_contexts`.
- Approval enforcement: `load_context` and `get_context` reject unapproved packets.
- Rate limiting: token-bucket rate limiter per session.
- Circuit breaker: pauses agent sessions exceeding repeated policy violations.

---

## 3. Security Invariants

1. **Zero Network Core:** Swallo's core package imports zero networking libraries (`socket`, `urllib.request`, `requests`, `httpx`). All operations are local to the machine.
2. **Mandatory Human-in-the-Loop Approval:** No agent can deliver or load context without interactive TTY confirmation from the human developer.
3. **Immutability of Packets:** Packets are content-addressed and cryptographically hashed; modifying packet contents changes the hash and invalidates approvals.
4. **Tamper-Evident Auditability:** Every write, approval, and delivery is recorded in an append-only HMAC chain verified by `swallo log --verify` and `swallo doctor`.
