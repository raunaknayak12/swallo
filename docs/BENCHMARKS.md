# Swallo Benchmark Suite & Performance Reference

> **Integrity & Disclosure Standard**<br>
> Every metric reported on this page was produced by scripts executed against Swallo v0.1.0 (commit `9c11c4e049`).<br>
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
| **High-Confidence Pattern Recall** | `100.0%` | >= 80.0% |
| **Pattern $F_1$ Score** | `1.0000` | >= 0.8800 |
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
| **Large Payload Bomb (>64 KB)** | Handled (`0.047s`) | Blocked at 64 KB cap |
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

| Payload Size | Median Latency | IQR | Std Dev | Throughput | Rounds / Warmups |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1 MB Transcript** | `0.182776s` | `0.051279s` | `0.027704s` | **`5.47 MB/s`** | 20 / 5 |
| **5 MB Transcript** | `0.741137s` | `0.037426s` | `0.033023s` | **`6.75 MB/s`** | 20 / 5 |

### 4.2 Canonical JSON Serialization & SHA-256 Hashing

| Packet Scale | Median Latency | IQR | Min / Max |
| :--- | :--- | :--- | :--- |
| **10 Items** | `0.102 ms` | `0.015 ms` | `0.085 ms` / `0.117 ms` |
| **100 Items** | `0.515 ms` | `0.041 ms` | `0.475 ms` / `0.623 ms` |
| **500 Items** | `2.424 ms` | `0.155 ms` | `2.322 ms` / `2.862 ms` |
| **1000 Items** | `5.026 ms` | `0.283 ms` | `4.853 ms` / `14.647 ms` |

### 4.3 SQLite WAL Throughput & MCP Latencies

- **SQLite WAL Write Throughput**: `902.4 writes/sec` (Median: `1.108143s` for 1000 writes).
- **MCP `list_contexts` Latency**: `3.75 ms` (IQR: `1.27 ms`).
- **MCP `save_context` (Draft) Latency**: `17.22 ms` (IQR: `1.36 ms`).
- **CLI Cold Start (`swallo --help`)**: `78.0 ms`.

---

## 5. Memory Profiling & Token Efficiency

- **Tracemalloc vs RSS Cross-Check**:
  - 1 MB Ingest: Tracemalloc peak: `3754 bytes`, Process RSS: `41.16 MB`.
  - 5 MB Ingest: Tracemalloc peak: `3362 bytes`, Process RSS: `45.44 MB`.
- **Token Reduction Efficiency**:
  - Raw Transcript Tokens (50 turns): `1175`
  - Compact Context Packet Tokens: `785`
  - Tokens Saved: `390` (33.19% reduction using `cl100k_base`).

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
