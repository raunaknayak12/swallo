# Context Packet Schema

**Status:** Draft v0.1 (`schema_version: "0.1"`). The packet is the core contract of the project. Publish the generated JSON Schema file alongside each release.

## 1. Principles

1. JSON is the stored and transported format. Readable Markdown is produced by renderers.
2. A packet is **data only**. Approval state is NOT in the packet; it lives in the local ledger (ADR-003).
3. Trust is **assigned by the tool on load**, never believed from the file (ADR-004).
4. Raw transcripts and artifacts live outside the packet in the content-addressed store and are referenced by hash, never by path (ADR-005).
5. Every item carries provenance.

## 2. Top-level structure

```json
{
  "schema_version": "0.1",
  "id": "pkt_8c1f2a",
  "created_at": "2026-10-25T10:00:00Z",
  "project": "myapp",
  "parent": null,
  "merged_from": [],
  "sources": [
    {
      "session_id": "s1",
      "agent": "chatgpt",
      "capture_method": "paste",
      "captured_at": "2026-10-25T09:55:00Z",
      "transcript": {"object": "sha256:ab12...", "redacted": true}
    }
  ],
  "goal": {"text": "Build an open-source context handoff tool"},
  "items": [
    {
      "id": "it_31c9",
      "kind": "decision",
      "text": "Ship as a pip package with an MCP server",
      "topic": "distribution",
      "value": "pip+mcp",
      "critical": false,
      "provenance": [{"session_id": "s1", "span": null}]
    },
    {
      "id": "it_77aa",
      "kind": "constraint",
      "text": "Core must run locally with no LLM key",
      "critical": true,
      "provenance": [{"session_id": "s1", "span": null}]
    }
  ],
  "conflicts": [],
  "repo_state": {"git_commit": "abc123", "dirty": false, "files": {"src/app.py": "blob:9f2c..."}},
  "redaction": {"count": 2, "types": ["api_key", "email"]}
}
```

## 3. Field reference

Example IDs in these docs are shortened for readability; real IDs follow section 6.

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | Major.minor; see section 8 |
| `id` | string | derived | `pkt_` + first 12 hex of the packet hash, extended on collision; never chosen by the producer; ignored on import and recomputed |
| `created_at` | RFC 3339 UTC | yes | |
| `project` | string | yes | Scopes the packet; loaders refuse cross-project loads by default |
| `parent` | string/null | no | Previous revision (resolve/edit creates a new revision) |
| `merged_from` | list of packet ids | no | Present on merge results |
| `sources[]` | object | yes | One per captured session |
| `sources[].agent` | string | yes | e.g. `chatgpt`, `claude`, `gemini`, `claude-code`, `cursor`, `antigravity` |
| `sources[].capture_method` | enum | yes | `export`, `paste`, `connector`, `ide-agent`, `manual` |
| `sources[].transcript` | object/null | no | `object` is a content hash; `redacted` states the stored copy's state |
| `goal` | object | yes | `text`; exactly one |
| `items[]` | object | yes | Decisions, constraints, questions, artifact references |
| `items[].kind` | enum | yes | `decision`, `constraint`, `question`, `artifact_ref` |
| `items[].topic` / `value` | string | no | Optional keys that make conflict detection precise |
| `items[].critical` | bool | no | Critical items are never trimmed by the token budget |
| `items[].provenance[]` | object | yes | `session_id`; `span` gives character offsets into the stored transcript when known |
| `conflicts[]` | object | no | See section 5 |
| `repo_state` | object/null | no | Commit, dirty flag, file blob hashes (repo-relative paths only) |
| `redaction` | object | no | Counts and types only, never matched text |

Items of kind `artifact_ref` reference stored objects by hash (`{"object": "sha256:..."}`) or repo-relative paths validated by the shared resolver (`repo/paths.py`). Absolute paths and `..` are rejected.

## 4. Trust tiers (assigned on load, not serialized as authoritative)

| Tier | Meaning |
|---|---|
| T0 | Typed or edited directly by the user at a CLI TTY |
| T1 | Written by the user's IDE agent through MCP |
| T2 | Model-written text pasted by the user |
| T3 | Imported file, shared packet, or raw export content |

A packet's tier is the lowest tier among its sources. Any `trust` field present in an incoming file is ignored. Delivery policy depends on tier (`TRD.md` section 7).

## 5. Conflicts

```json
{
  "id": "cf_01",
  "items": ["it_31c9", "it_9d02"],
  "reason": "same_topic_different_value",
  "status": "unresolved",
  "resolution": null
}
```

`reason` values: `same_topic_different_value`, `override_language`, `heuristic_negation`. `status`: `unresolved` or `resolved` (with `resolution`: kept item id, or `both_valid`). Resolving creates a new packet revision with a new hash.

## 6. Canonicalization, hashing and IDs

**Canonical form** ("swallo canonical JSON v1", our own definition, not RFC 8785, golden-tested):

1. UTF-8 without BOM; no insignificant whitespace; separators `,` and `:`.
2. Object keys sorted by Unicode code point; duplicate keys are rejected at parse time.
3. Strings are normalized to NFC at ingest and encoded as Python's JSON encoder does with `ensure_ascii=False`; lone surrogates are rejected.
4. Numbers: integers only, within +/-(2^53 - 1). Floats, NaN and Infinity are rejected anywhere in a packet. Booleans and null are allowed.
5. Consequence for the schema: no field may hold a float. If a score is ever needed, use an integer (for example basis points) or an enum label.

**Hashed form:** the canonical form of the packet with volatile fields removed: `id`, `created_at`, and every `sources[*].captured_at`. They are excluded so that identical content saved at different times has the same hash (deduplication and approval binding) and because `id` is itself derived from the hash.

**Hash:** `sha256:` followed by the hex SHA-256 of the canonical bytes of the hashed form.

**Packet ID:** `pkt_` plus the first 12 hex characters of the hash. If it collides with a different hash in the same store, extend it by two characters until unique.

**Item ID (proposal):** `it_` plus the first 8 hex characters of SHA-256 over `kind`, a NUL byte, and the NFC-normalized text; extend on collision within a packet. Producer-supplied IDs are ignored.

**Approvals** bind to the full hash. Changing any hashed field changes the hash and therefore requires re-approval.

**Golden files:** committed canonical bytes and hashes for a fixture per schema version. Any change to canonicalization requires a schema major version bump.

## 7. Validation limits (proposals, configurable)

- Item text at most 2,000 characters; at most 500 items per kind; packet at most 1 MiB.
- JSON nesting depth at most 16; unknown top-level fields rejected in strict mode, preserved under `x_` prefixes in lenient mode.
- Control characters in text fields are rejected or stripped at load.

## 8. Versioning and migration

- `schema_version` is `major.minor`. Minor additions are backward compatible (new optional fields). Major changes break readers.
- Every released version keeps a fixture; CI loads all fixtures through migrators to the current version.
- Readers MUST reject a major version they do not understand, with a clear message.
- The JSON Schema is generated from the Pydantic models and committed per release.

## 9. Not in the packet

- Approval status (ledger)
- Raw transcripts and artifact bytes (object store)
- Secret values or matched text (only counts and types)
- Absolute filesystem paths
