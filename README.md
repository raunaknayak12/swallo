# swallo

Portable, reviewable handoff between any chat agent and any IDE, with reproducible evidence that it works.

> **Status:** Design stage. Nothing released yet. Do not install from package indexes; no published releases exist.

## Overview

`swallo` is an open-source, pure-Python project designed to transport structured conversational and debugging context between AI coding assistants, chat interfaces (ChatGPT, Claude, Gemini), and agentic IDE environments (Claude Code, Cursor, Antigravity).

Context travels as an integrity-checked, schema-validated JSON "context packet" with cryptographic content addressing, deterministic canonicalization, explicit redaction bounds, and zero network calls in the core runtime.

## Documentation

Comprehensive design specifications and architecture documentation are located in [`docs/`](docs/):

- [Documentation Overview](docs/README.md)
- [Product Requirements Document (PRD)](docs/PRD.md)
- [Technical Requirements Document (TRD)](docs/TRD.md)
- [Architecture & Design Decisions](docs/DECISIONS.md)
- [Context Packet Schema](docs/PACKET_SCHEMA.md)
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
- [Threat Model & Security Design](docs/Security.md)
- [Benchmarks & Claims Policy](docs/BENCHMARKS.md)
- [Roadmap & Milestones](docs/ROADMAP.md)

## License

This project is licensed under the [MIT License](LICENSE).
