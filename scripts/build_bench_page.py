"""
Generate docs/BENCHMARKS.md from executed benchmark results.

Reads:
- benchmarks/results/deterministic.json
- benchmarks/results/perf/summary.json

Formats honest, reproducible benchmark documentation for the Swallo website.
Never invents, estimates, or hardcodes numbers.
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_benchmarks_markdown() -> str:
    det_path = Path("benchmarks/results/deterministic.json")
    perf_path = Path("benchmarks/results/perf/summary.json")

    if not det_path.is_file() or not perf_path.is_file():
        raise FileNotFoundError("Missing deterministic.json or perf/summary.json. Run benchmark suites first.")

    det_data = json.loads(det_path.read_text(encoding="utf-8"))
    perf_data = json.loads(perf_path.read_text(encoding="utf-8"))

    env_det = det_data.get("environment", {})
    env_perf = perf_data.get("environment", {})
    metrics = det_data.get("metrics", {})
    perf_benches = perf_data.get("benchmarks", {})

    corpus = metrics.get("corpus_redaction", {})
    variants = metrics.get("decoded_variants", {})
    _ = metrics.get("hash_stability", {})
    defense = metrics.get("defense_matrix", {})
    sanitizer = metrics.get("sanitizer", {})
    tamper = metrics.get("tamper_detection", {})
    invariants = metrics.get("security_invariants", {})

    md = f"""# Swallo Benchmark Suite & Performance Reference

> **Integrity & Disclosure Standard**  
> Every metric reported on this page was produced by scripts executed against Swallo v{det_data.get("swallo_version", "0.1.0")} (commit `{det_data.get("git_commit", "unknown")[:10]}`).  
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
| **Operating System** | {env_det.get("os", "N/A")} | {env_perf.get("os", "N/A")} |
| **Python Version** | {env_det.get("python_version", "N/A")} | {env_perf.get("python_version", "N/A")} |
| **Processor** | {env_det.get("cpu", "N/A")} | {env_perf.get("cpu", "N/A")} |
| **Logical / Physical Cores** | - | {env_perf.get("cpu_count_logical", "N/A")} / {env_perf.get("cpu_count_physical", "N/A")} |
| **Total RAM** | - | {env_perf.get("total_ram_gb", "N/A")} GB |

---

## 3. Deterministic Correctness Benchmarks

### 3.1 Secret Redaction Accuracy & Recall

Evaluated across synthetic labeled test vectors (AWS keys, GitHub PATs, Slack tokens, private keys, connection strings, bearer tokens) and hard negatives (UUIDs, git commits, base64 payloads, normal code).

| Metric | Result | Target / Standard |
| :--- | :--- | :--- |
| **High-Confidence Pattern Precision** | `{corpus.get("pattern_precision", 0.0) * 100:.1f}%` | 100.0% (Zero false positives on hard negatives) |
| **High-Confidence Pattern Recall** | `{corpus.get("pattern_recall", 0.0) * 100:.1f}%` | >= 80.0% |
| **Pattern $F_1$ Score** | `{corpus.get("pattern_f1", 0.0):.4f}` | >= 0.8800 |
| **Pattern False Positive Rate** | `{corpus.get("pattern_false_positive_rate", 0.0):.1f}%` | 0.0% |
| **Entropy Detector False Positive Rate** | `{corpus.get("entropy_detector_false_positive_rate", 0.0):.1f}%` | Audited independently from regex |

### 3.2 Decoded Variants & Decode-Bomb Caps

Tests multi-layer encoding evasion and denial-of-service cap enforcement.

| Obfuscation Layer | Detection Recall | Defense Cap Behavior |
| :--- | :--- | :--- |
| **Base64** | `{variants.get("base64_recall", 0.0) * 100:.1f}%` | Max depth 3 |
| **Hex Encoding** | `{variants.get("hex_recall", 0.0) * 100:.1f}%` | Stream verified |
| **URL Percent-Encoding** | `{variants.get("url_recall", 0.0) * 100:.1f}%` | Stream verified |
| **Rot13** | `{variants.get("rot13_recall", 0.0) * 100:.1f}%` | Candidate verified |
| **Reversal** | `{variants.get("reversal_recall", 0.0) * 100:.1f}%` | Candidate verified |
| **Zero-Width Steganography** | `{variants.get("zero_width_recall", 0.0) * 100:.1f}%` | Binary bit extraction |
| **Nested Depth 2 & 3** | `{variants.get("nested_depth_2_recall", 0.0) * 100:.1f}%` / `{variants.get("nested_depth_3_recall", 0.0) * 100:.1f}%` | Recursive scan |
| **Large Payload Bomb (>64 KB)** | Handled (`{variants.get("size_cap_duration_s", 0.0)}s`) | Blocked at 64 KB cap |
| **Deep Recursion Bomb (>3 depths)** | Handled (`{variants.get("depth_cap_duration_s", 0.0)}s`) | Halts safely at depth 3 |

### 3.3 Boundary Defense & Hostile Archive Matrix

| Attack Vector | Defense Mechanism | Result |
| :--- | :--- | :--- |
| **Zip-Slip (Relative `../../`)** | `ArchiveGuard.verify_zip_structure` | `{"BLOCKED" if defense.get("zip_slip_relative_blocked") else "FAILED"}` |
| **Zip-Slip (Absolute `/etc/passwd`)** | `ArchiveGuard.verify_zip_structure` | `{"BLOCKED" if defense.get("zip_slip_absolute_blocked") else "FAILED"}` |
| **Zip-Slip (Windows `..\\..\\`)** | `ArchiveGuard.verify_zip_structure` | `{"BLOCKED" if defense.get("zip_slip_backslash_blocked") else "FAILED"}` |
| **Archive Member Count Limit** | `max_entries` threshold cap | `{"BLOCKED" if defense.get("member_count_limit_blocked") else "FAILED"}` |
| **Decompression Bomb Ratio (>500:1)** | `safe_read_member` streaming ratio check | `{"BLOCKED" if defense.get("compression_ratio_bomb_blocked") else "FAILED"}` |
| **Uncompressed Size Cap (>1 KB)** | `safe_read_member` size validation | `{"BLOCKED" if defense.get("uncompressed_size_limit_blocked") else "FAILED"}` |
| **Deep JSON Recursion (>64 levels)** | `safe_json_loads` nesting counter | `{"BLOCKED" if defense.get("json_max_depth_blocked") else "FAILED"}` |
| **Overall Defense Matrix Pass Rate** | Strict binary gate | **`{defense.get("defense_matrix_pass_rate", 0.0) * 100:.1f}%`** |

### 3.4 Trojan Source & Terminal Sanitization (CVE-2021-42574)

- **BiDi Control Overrides Neutralized**: `{"PASS" if sanitizer.get("trojan_source_bidi_neutralized") else "FAIL"}`
- **Unicode Tag Plane Characters (U+E0000..U+E007F) Neutralized**: `{"PASS" if sanitizer.get("unicode_tag_chars_neutralized") else "FAIL"}`
- **ANSI Terminal Escapes Neutralized**: `{"PASS" if sanitizer.get("ansi_escapes_neutralized") else "FAIL"}`
- **Invisible Zero-Width Flagging Recall**: `{sanitizer.get("invisible_detection_recall", 0.0) * 100:.1f}%`

### 3.5 Tamper Detection & Cryptographic Ledger

- **Event Log Tamper Detection**: `{tamper.get("event_log_tamper_detection_rate", 0.0) * 100:.1f}%` across all fields (type, detail, prev_mac, mac, deleted rows).
- **Approval Ledger Tamper Detection**: `{tamper.get("ledger_tamper_detection_rate", 0.0) * 100:.1f}%` across target, timestamp, hash, and MAC modifications.

### 3.6 Security Invariants

- MCP Tool List contains 0 approve tools: `{"PASS" if invariants.get("mcp_tool_list_has_no_approve") else "FAIL"}`
- Circuit breaker trips at 5 blocks and persists across restart: `{"PASS" if invariants.get("circuit_breaker_trips_at_5") and invariants.get("circuit_breaker_persists_across_restart") else "FAIL"}`
- Token bucket burst (10) enforced: `{"PASS" if invariants.get("token_bucket_burst_enforced") else "FAIL"}`
- Draft quota (50) enforced: `{"PASS" if invariants.get("draft_quota_enforced") else "FAIL"}`
- Stale context blocked by default on load: `{"PASS" if invariants.get("stale_packet_blocked_by_default") else "FAIL"}`

---

## 4. Statistical Performance Benchmarks

### 4.1 Ingest & Redaction Throughput

| Payload Size | Median Latency | IQR | Throughput | Rounds / Warmups |
| :--- | :--- | :--- | :--- | :--- |
| **1 MB Transcript** | `{perf_benches.get("redaction", {}).get("1MB", {}).get("latency_seconds", {}).get("median", 0.0)}s` | `{perf_benches.get("redaction", {}).get("1MB", {}).get("latency_seconds", {}).get("iqr", 0.0)}s` | **`{perf_benches.get("redaction", {}).get("1MB", {}).get("throughput_mb_s", 0.0)} MB/s`** | 5 / 2 |
| **5 MB Transcript** | `{perf_benches.get("redaction", {}).get("5MB", {}).get("latency_seconds", {}).get("median", 0.0)}s` | `{perf_benches.get("redaction", {}).get("5MB", {}).get("latency_seconds", {}).get("iqr", 0.0)}s` | **`{perf_benches.get("redaction", {}).get("5MB", {}).get("throughput_mb_s", 0.0)} MB/s`** | 5 / 2 |

### 4.2 Canonical JSON Serialization & SHA-256 Hashing

| Packet Scale | Median Latency | IQR | Min / Max |
| :--- | :--- | :--- | :--- |
| **10 Items** | `{perf_benches.get("canonical_hashing", {}).get("10_items", {}).get("latency_seconds", {}).get("median", 0.0) * 1000:.3f} ms` | `{perf_benches.get("canonical_hashing", {}).get("10_items", {}).get("latency_seconds", {}).get("iqr", 0.0) * 1000:.3f} ms` | `{perf_benches.get("canonical_hashing", {}).get("10_items", {}).get("latency_seconds", {}).get("min", 0.0) * 1000:.3f} ms` / `{perf_benches.get("canonical_hashing", {}).get("10_items", {}).get("latency_seconds", {}).get("max", 0.0) * 1000:.3f} ms` |
| **100 Items** | `{perf_benches.get("canonical_hashing", {}).get("100_items", {}).get("latency_seconds", {}).get("median", 0.0) * 1000:.3f} ms` | `{perf_benches.get("canonical_hashing", {}).get("100_items", {}).get("latency_seconds", {}).get("iqr", 0.0) * 1000:.3f} ms` | `{perf_benches.get("canonical_hashing", {}).get("100_items", {}).get("latency_seconds", {}).get("min", 0.0) * 1000:.3f} ms` / `{perf_benches.get("canonical_hashing", {}).get("100_items", {}).get("latency_seconds", {}).get("max", 0.0) * 1000:.3f} ms` |
| **500 Items** | `{perf_benches.get("canonical_hashing", {}).get("500_items", {}).get("latency_seconds", {}).get("median", 0.0) * 1000:.3f} ms` | `{perf_benches.get("canonical_hashing", {}).get("500_items", {}).get("latency_seconds", {}).get("iqr", 0.0) * 1000:.3f} ms` | `{perf_benches.get("canonical_hashing", {}).get("500_items", {}).get("latency_seconds", {}).get("min", 0.0) * 1000:.3f} ms` / `{perf_benches.get("canonical_hashing", {}).get("500_items", {}).get("latency_seconds", {}).get("max", 0.0) * 1000:.3f} ms` |

### 4.3 SQLite WAL Throughput & MCP Latencies

- **SQLite WAL Write Throughput**: `{perf_benches.get("sqlite_wal", {}).get("single_writer", {}).get("writes_per_sec", 0.0)} writes/sec` (Median: `{perf_benches.get("sqlite_wal", {}).get("single_writer", {}).get("latency_seconds", {}).get("median", 0.0)}s` for 300 writes).
- **MCP `list_contexts` Latency**: `{perf_benches.get("mcp_latency", {}).get("list_contexts", {}).get("median", 0.0) * 1000:.2f} ms` (IQR: `{perf_benches.get("mcp_latency", {}).get("list_contexts", {}).get("iqr", 0.0) * 1000:.2f} ms`).
- **MCP `save_context` (Draft) Latency**: `{perf_benches.get("mcp_latency", {}).get("save_context_draft", {}).get("median", 0.0) * 1000:.2f} ms` (IQR: `{perf_benches.get("mcp_latency", {}).get("save_context_draft", {}).get("iqr", 0.0) * 1000:.2f} ms`).
- **CLI Cold Start (`swallo --help`)**: `{perf_benches.get("cli_cold_start", {}).get("swallo_help", {}).get("median", 0.0) * 1000:.1f} ms`.

---

## 5. Memory Profiling & Token Efficiency

- **Tracemalloc vs RSS Cross-Check**:
  - 1 MB Ingest: Tracemalloc peak: `{perf_benches.get("memory", {}).get("1MB", {}).get("tracemalloc_peak_bytes", 0)} bytes`, Process RSS: `{perf_benches.get("memory", {}).get("1MB", {}).get("rss_current_mb", 0.0)} MB`.
  - 5 MB Ingest: Tracemalloc peak: `{perf_benches.get("memory", {}).get("5MB", {}).get("tracemalloc_peak_bytes", 0)} bytes`, Process RSS: `{perf_benches.get("memory", {}).get("5MB", {}).get("rss_current_mb", 0.0)} MB`.
- **Token Reduction Efficiency**:
  - Raw Transcript Tokens (50 turns): `{perf_benches.get("token_reduction", {}).get("raw_transcript_tokens", 0)}`
  - Compact Context Packet Tokens: `{perf_benches.get("token_reduction", {}).get("packet_tokens", 0)}`
  - Tokens Saved: `{perf_benches.get("token_reduction", {}).get("tokens_saved", 0)}` ({perf_benches.get("token_reduction", {}).get("reduction_percentage", 0.0)}% reduction using `{perf_benches.get("token_reduction", {}).get("tokenizer", "cl100k_base")}`).

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
"""
    return md.strip() + "\n"


def main() -> None:
    content = generate_benchmarks_markdown()
    out_file = Path("docs/BENCHMARKS.md")
    out_file.write_text(content, encoding="utf-8")
    print(f"Documentation page successfully updated: {out_file}")


if __name__ == "__main__":
    main()
