# Swallo Benchmark Suite & Performance Reference

> **Integrity & Disclosure Standard**  
> Every metric reported on this page was produced by scripts executed against Swallo v0.1.0 (commit `450ea0d186`).  
> No numbers are estimated or hardcoded. No prompt-injection detection rates are claimed; only structural defense invariants are tested.

---

## 1. Methodology & Test Split

Benchmarks in Swallo are strictly split into two categories per Benchtop Labs standards:

1. **Deterministic Benchmarks (Exact / Verifiable)**: Checked via `swallo bench verify`. Zero-tolerance pass/fail matrices asserting algorithmic properties, redaction precision/recall, canonical hash stability, and tamper resistance.
2. **Statistical Benchmarks (Latency / Memory / Throughput)**: Measured across warmups and multi-sample rounds. Reported as **Median + IQR** (Interquartile Range) to eliminate outlier noise. Timing benchmarks **never** run inside main CI test suites.

---

## 2. Test Environment

| Property | Deterministic Suite | Statistical Perf Suite |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 | Windows 11 |
| **Python Version** | 3.12.10 | 3.12.10 |
| **Processor** | AMD64 Family 25 Model 124 Stepping 0, AuthenticAMD | AMD64 Family 25 Model 124 Stepping 0, AuthenticAMD |
| **Logical / Physical Cores** | - | 12 / 6 |
| **Total RAM** | - | 15.23 GB |

---

## 3. Deterministic Correctness Benchmarks

### 3.1 Secret Redaction Accuracy & Recall

Evaluated across synthetic labeled test vectors (AWS keys, GitHub PATs, Slack tokens, private keys, connection strings, bearer tokens) and hard negatives (UUIDs, git commits, base64 payloads, normal code).

| Metric | Result | Target / Standard |
| :--- | :--- | :--- |
| **High-Confidence Pattern Precision** | `100.0%` | 100.0% (Zero false positives on hard negatives) |
| **High-Confidence Pattern Recall** | `80.0%` | >= 80.0% |
| **Pattern $F_1$ Score** | `0.8889` | >= 0.8800 |
| **Pattern False Positive Rate** | `0.0%` | 0.0% |
| **Entropy Detector False Positive Rate** | `0.0%` | Audited independently from regex |

### 3.2 Decoded Variants & Decode-Bomb Caps

Tests multi-layer encoding evasion and denial-of-service cap enforcement.

| Obfuscation Layer | Detection Recall | Defense Cap Behavior |
| :--- | :--- | :--- |
| **Base64** | `100.0%` | Max depth 3 |
| **Hex Encoding** | `100.0%` | Stream verified |
| **URL Percent-Encoding** | `100.0%` | Stream verified |
| **Rot13** | `100.0%` | Candidate verified |
| **Reversal** | `100.0%` | Candidate verified |
| **Zero-Width Steganography** | `100.0%` | Binary bit extraction |
| **Nested Depth 2 & 3** | `100.0%` / `100.0%` | Recursive scan |
| **Large Payload Bomb (>64 KB)** | Handled (`0.063s`) | Blocked at 64 KB cap |
| **Deep Recursion Bomb (>3 depths)** | Handled (`0.0s`) | Halts safely at depth 3 |

### 3.3 Boundary Defense & Hostile Archive Matrix

| Attack Vector | Defense Mechanism | Result |
| :--- | :--- | :--- |
| **Zip-Slip (Relative `../../`)** | `ArchiveGuard.verify_zip_structure` | `BLOCKED` |
| **Zip-Slip (Absolute `/etc/passwd`)** | `ArchiveGuard.verify_zip_structure` | `BLOCKED` |
| **Zip-Slip (Windows `..\..\`)** | `ArchiveGuard.verify_zip_structure` | `BLOCKED` |
| **Archive Member Count Limit** | `max_entries` threshold cap | `BLOCKED` |
| **Decompression Bomb Ratio (>500:1)** | `safe_read_member` streaming ratio check | `BLOCKED` |
| **Uncompressed Size Cap (>1 KB)** | `safe_read_member` size validation | `BLOCKED` |
| **Deep JSON Recursion (>64 levels)** | `safe_json_loads` nesting counter | `BLOCKED` |
| **Overall Defense Matrix Pass Rate** | Strict binary gate | **`100.0%`** |

### 3.4 Trojan Source & Terminal Sanitization (CVE-2021-42574)

- **BiDi Control Overrides Neutralized**: `PASS`
- **Unicode Tag Plane Characters (U+E0000..U+E007F) Neutralized**: `PASS`
- **ANSI Terminal Escapes Neutralized**: `PASS`
- **Invisible Zero-Width Flagging Recall**: `100.0%`

### 3.5 Tamper Detection & Cryptographic Ledger

- **Event Log Tamper Detection**: `100.0%` across all fields (type, detail, prev_mac, mac, deleted rows).
- **Approval Ledger Tamper Detection**: `100.0%` across target, timestamp, hash, and MAC modifications.

### 3.6 Security Invariants

- MCP Tool List contains 0 approve tools: `PASS`
- Circuit breaker trips at 5 blocks and persists across restart: `PASS`
- Token bucket burst (10) enforced: `PASS`
- Draft quota (50) enforced: `PASS`
- Stale context blocked by default on load: `PASS`

---

## 4. Statistical Performance Benchmarks

### 4.1 Ingest & Redaction Throughput

| Payload Size | Median Latency | IQR | Throughput | Rounds / Warmups |
| :--- | :--- | :--- | :--- | :--- |
| **1 MB Transcript** | `0.251292s` | `0.005833s` | **`3.98 MB/s`** | 5 / 2 |
| **5 MB Transcript** | `0.832892s` | `0.014402s` | **`6.0 MB/s`** | 5 / 2 |

### 4.2 Canonical JSON Serialization & SHA-256 Hashing

| Packet Scale | Median Latency | IQR | Min / Max |
| :--- | :--- | :--- | :--- |
| **10 Items** | `0.069 ms` | `0.005 ms` | `0.064 ms` / `0.078 ms` |
| **100 Items** | `0.493 ms` | `0.016 ms` | `0.483 ms` / `0.633 ms` |
| **500 Items** | `2.459 ms` | `0.141 ms` | `2.370 ms` / `3.204 ms` |

### 4.3 SQLite WAL Throughput & MCP Latencies

- **SQLite WAL Write Throughput**: `887.0 writes/sec` (Median: `0.338237s` for 300 writes).
- **MCP `list_contexts` Latency**: `3.19 ms` (IQR: `0.91 ms`).
- **MCP `save_context` (Draft) Latency**: `3.79 ms` (IQR: `0.59 ms`).
- **CLI Cold Start (`swallo --help`)**: `211.9 ms`.

---

## 5. Memory Profiling & Token Efficiency

- **Tracemalloc vs RSS Cross-Check**:
  - 1 MB Ingest: Tracemalloc peak: `3355 bytes`, Process RSS: `39.95 MB`.
  - 5 MB Ingest: Tracemalloc peak: `3334 bytes`, Process RSS: `43.96 MB`.
- **Token Reduction Efficiency**:
  - Raw Transcript Tokens (50 turns): `2600`
  - Compact Context Packet Tokens: `2538`
  - Tokens Saved: `62` (2.38% reduction using `cl100k_base`).

---

## 6. How to Reproduce

All benchmarks are strictly reproducible using the committed scripts:

```bash
# 1. Deterministic suite (generates benchmarks/results/deterministic.json)
python -m benchmarks.deterministic.runner

# 2. Cryptographic and metric verification
swallo bench verify benchmarks/results/deterministic.json

# 3. Statistical performance suite (generates benchmarks/results/perf/summary.json)
python -m benchmarks.perf.runner

# 4. Regenerate this documentation page
python scripts/build_bench_page.py
```
