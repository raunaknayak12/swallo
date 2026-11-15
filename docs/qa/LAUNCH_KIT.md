# Swallo v0.1.4 Launch Kit

## 1. GitHub Release Notes (v0.1.4)

### Release Title: Swallo v0.1.4: Deterministic Benchmarks, CLI Routing & Security Hardening

**Swallo** is a zero-network, local ledger for LLM agent context handoffs with interactive human-in-the-loop approval.

> [!NOTE]
> Swallo is v0.1 software and has **not** been independently audited. It is not a replacement for dedicated secret scanners.

### What's Changed in v0.1.4
* **CLI & Error Handling**:
  - Subcommands routed through `_dispatch_subcommand` with clean, user-actionable error messages.
  - No Python tracebacks on missing arguments or `pydantic.ValidationError`.
* **Packaging & Compatibility**:
  - Pinned `mcp` SDK to `>=1.2.0,<2.0.0` to ensure `FastMCP` compatibility across all supported environments.
  - Full support for Python 3.11, 3.12, and 3.13 across Ubuntu, macOS, and Windows.
* **Deterministic Benchmarking**:
  - Added strict row-change preconditions to all benchmark tamper mutations.
  - Fixed mutation no-op edge cases (e.g. MAC prefix collisions).
  - Verified 100% deterministic detection rate across 200 consecutive CI iterations.
* **Documentation & Safety**:
  - Added explicit *Known Limitations* (entropy false positives, redaction boundaries, Windows .exe execution note).
  - Added structured Issue Templates for reproducible bug reports and feature requests.
  - Published comprehensive Security Policy with private reporting channels.

### Quick Start
```bash
pip install swallo
swallo init
swallo doctor
```
For MCP server integration:
```bash
pip install "swallo[mcp]"
python -m swallo mcp serve
```

---

## 2. Public Launch Announcement Copy

### Title: Swallo v0.1.4 — Transparent, Local Context Handoff for Coding Agents

We are sharing **Swallo v0.1.4**, an open-source, local-first context handoff tool for multi-agent workflows.

When agents hand off tasks or code context across sessions, context rot and uninspected data transfers can introduce subtle bugs or unwanted state. Swallo introduces an auditable, append-only local SQLite ledger that enforces human approval before context packets can be consumed by other agents.

**Key Invariants:**
- **Zero Network**: The core runtime performs zero external network calls.
- **Interactive Approval**: Terminal-based interactive review gate (no `--force` bypass).
- **Redaction Engine**: High-entropy secret and credential redaction before ledger entry.
- **Audit Ledger**: HMAC-SHA256 authenticated chain of approved context packets.

**Status & Limitations:**
Swallo is v0.1 software and is not independently audited. It does not detect prompt injection and is not a replacement for full enterprise secret scanners.

- **GitHub**: https://github.com/raunaknayak12/swallo
- **PyPI**: https://pypi.org/project/swallo/0.1.4/
- **Documentation**: https://github.com/raunaknayak12/swallo#readme

---

## 3. Launch-Day Monitoring Checklist

1. **GitHub Issues & Discussions**:
   - Check https://github.com/raunaknayak12/swallo/issues for any initial installation issues or questions.
   - For bug reports, verify environment using `swallo doctor` output provided by the user.
2. **PyPI Status**:
   - Confirm PyPI package page renders cleanly with Markdown formatting and license classifiers.
   - Verify attestations badge on PyPI.
3. **CI & Workflows**:
   - Monitor scheduled or triggered runs on GitHub Actions to ensure ongoing health.
4. **Reproduction Template**:
   ```bash
   python -m venv test-env
   source test-env/bin/activate  # or test-env\Scripts\activate on Windows
   pip install swallo==0.1.4
   swallo --version
   swallo doctor
   ```
