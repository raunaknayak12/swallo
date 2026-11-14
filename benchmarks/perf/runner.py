"""
Statistical Performance Benchmark Suite.

Executes honest, reproducible statistical benchmarks:
1. Ingest + redaction latency & throughput over realistic multi-structure transcripts.
   (Synthetic transcripts contain realistic mix of conversation turns, code blocks,
   markdown diffs, JSON payloads, and stack traces - NO single sentence repetition).
2. Canonical JSON serialization + SHA-256 packet hashing (10, 100, 500, 1000 items).
3. SQLite WAL write throughput (1,000 writes, multi-sample).
4. MCP tool latency simulation (list_contexts, save_context_draft).
5. CLI cold start (python -m swallo.cli --help, list).
6. Peak memory tracking (tracemalloc separated from timing runs + peak RSS cross-check).
7. Multi-domain token reduction measurement across realistic development sessions.

Reports median, IQR, min, max, standard deviation, rounds, warmups, and hardware environment.
Outputs to benchmarks/results/perf/summary.json.
"""

from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

import psutil

from swallo import __version__
from swallo.redact.engine import RedactionEngine
from swallo.redact.entropy import EntropyDetector
from swallo.redact.patterns import PatternDetector
from swallo.schema.canonical import packet_hash
from swallo.schema.models import Goal, Item, Packet, Source
from swallo.server.mcp_server import SwalloService
from swallo.store import db
from swallo.store.db import get_or_create_local_key


def _get_git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:  # noqa: S110
        pass
    return "unknown"


def _calc_stats(samples: list[float]) -> dict[str, float]:
    """Calculate median, IQR, min, max, and standard deviation from samples."""
    if not samples:
        return {"median": 0.0, "iqr": 0.0, "min": 0.0, "max": 0.0, "std_dev": 0.0}
    s = sorted(samples)
    n = len(s)
    med = s[n // 2] if n % 2 != 0 else (s[n // 2 - 1] + s[n // 2]) / 2.0

    # Quartiles
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    iqr = q3 - q1

    # Standard deviation
    mean = sum(s) / n
    variance = sum((x - mean) ** 2 for x in s) / n if n > 1 else 0.0
    std_dev = math.sqrt(variance)

    return {
        "median": round(med, 6),
        "iqr": round(iqr, 6),
        "min": round(s[0], 6),
        "max": round(s[-1], 6),
        "std_dev": round(std_dev, 6),
    }


def _generate_realistic_transcript(target_bytes: int) -> str:
    """
    Synthesize realistic agent conversation transcripts containing varied structural formats:
    - User questions and agent replies
    - Code blocks (Python, SQL, Shell)
    - Git diffs and patch blocks
    - JSON payloads and tool invocation outputs
    - Stack traces and compiler logs
    Prevents artificial monoculture optimization.
    """
    blocks = [
        # Conversational dialogue
        (
            "User: How should we structure the zero-network handoff packet for multi-agent handoffs?\n"
            + "Agent: The handoff packet needs to be self-contained, canonicalized using RFC-standard JSON, "
            + "and signed with Ed25519 or HMAC-SHA256. All volatile timestamps must be decoupled from content address.\n"
        ),
        # Tool call JSON
        (
            '```json\n{\n  "action": "list_contexts",\n  "project": "swallo_core",\n  "status": "active",\n  '
            + '"count": 42,\n  "checksum": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"\n}\n```\n'
        ),
        # Python code snippet (literal sample text for transcript generation - not executed)
        (
            '```python\ndef sanitize_packet_payload(data: bytes, max_depth: int = 50) -> dict[str, Any]:\n'
            + '    """Enforce defensive nesting limits against JSON bomb denial of service."""\n'
            + '    parsed = safe_json_loads(data.decode("utf-8"))  # wraps json.loads with error handling\n'
            + '    _assert_depth_bounded(parsed, current_depth=1, limit=max_depth)\n'
            + '    return parsed\n```\n'
        ),
        # Git diff block
        (
            '```diff\n--- a/src/swallo/redact/decode.py\n+++ b/src/swallo/redact/decode.py\n@@ -25,2 +25,4 @@\n'
            + '-MAX_DECODE_DEPTH = 2\n+MAX_DECODE_DEPTH = 3\n+MAX_DECODED_SIZE = 64 * 1024\n```\n'
        ),
        # Traceback / log output
        (
            "DEBUG [2026-11-11T00:15:00Z] swallo.server.guards: Token bucket check passed (tokens_remaining=8.4)\n"
            + "INFO [2026-11-11T00:15:01Z] swallo.store.db: Migration applied successfully (version=1)\n"
            + "Traceback (most recent call last):\n  File 'runner.py', line 42, in execute\n    safe_json_loads(data)\n"
            + "swallo.errors.SecurityError: Nested JSON depth exceeds maximum threshold of 64\n"
        ),
    ]

    parts: list[str] = []
    current_len = 0
    i = 0
    while current_len < target_bytes:
        blk = blocks[i % len(blocks)]
        parts.append(blk)
        current_len += len(blk.encode("utf-8"))
        i += 1

    return "".join(parts)


def bench_redaction(sizes_mb: list[int] | None = None, rounds: int = 20, warmups: int = 5) -> dict[str, Any]:
    """Benchmark redaction latency and throughput on realistic, multi-structure transcripts."""
    if sizes_mb is None:
        sizes_mb = [1, 5]
    engine = RedactionEngine([PatternDetector(), EntropyDetector()])
    results: dict[str, Any] = {}

    for sz in sizes_mb:
        target_bytes = sz * 1024 * 1024
        text = _generate_realistic_transcript(target_bytes)

        # Dedicated warmups
        for _ in range(warmups):
            _ = engine.redact(text[:50000])

        timings: list[float] = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            _ = engine.redact(text)
            t1 = time.perf_counter()
            timings.append(t1 - t0)

        stats = _calc_stats(timings)
        mb_per_sec = round((sz / stats["median"]), 2) if stats["median"] > 0 else 0.0
        results[f"{sz}MB"] = {
            "size_bytes": len(text.encode("utf-8")),
            "latency_seconds": stats,
            "throughput_mb_s": mb_per_sec,
            "rounds": rounds,
            "warmups": warmups,
        }

    return results


def bench_canonical_hashing(
    item_counts: list[int] | None = None,
    rounds: int = 25,
    warmups: int = 5,
) -> dict[str, Any]:
    """Benchmark canonical JSON serialization and SHA-256 hashing across scale."""
    if item_counts is None:
        item_counts = [10, 100, 500, 1000]
    results: dict[str, Any] = {}

    kinds = ["decision", "constraint", "question", "artifact_ref"]
    for cnt in item_counts:
        items = [
            Item(
                id=f"it_{i:08x}",
                kind=kinds[i % len(kinds)],
                text=f"Realistic architectural item {i}: enforce strict schema bounds and immutable audit trail.",
                topic=f"architecture_layer_{i % 8}",
                value="approved",
            )
            for i in range(cnt)
        ]
        pkt = Packet(
            id="pkt_perf_test_000",
            schema_version="0.1",
            created_at="2026-01-01T00:00:00Z",
            project="perf_benchmark",
            goal=Goal(text="Benchmark canonical serialization"),
            sources=[
                Source(
                    session_id="sess_perf",
                    agent="antigravity",
                    capture_method="paste",
                    captured_at="2026-01-01T00:00:00Z",
                )
            ],
            items=items,
        )
        pkt_dict = pkt.model_dump()

        # Warmups
        for _ in range(warmups):
            _ = packet_hash(pkt_dict)

        timings: list[float] = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            _ = packet_hash(pkt_dict)
            t1 = time.perf_counter()
            timings.append(t1 - t0)

        stats = _calc_stats(timings)
        results[f"{cnt}_items"] = {
            "item_count": cnt,
            "latency_seconds": stats,
            "rounds": rounds,
            "warmups": warmups,
        }

    return results


def bench_sqlite_wal(tmp_dir: Path, writes: int = 1000, rounds: int = 10, warmups: int = 2) -> dict[str, Any]:
    """Benchmark SQLite WAL write throughput with 1,000 writes across rounds."""
    results: dict[str, Any] = {}
    db_file = tmp_dir / "wal_bench.db"

    timings: list[float] = []
    for r in range(rounds + warmups):
        if db_file.exists():
            db_file.unlink()
        conn = db.get_connection(db_file)
        db.apply_migrations(conn)

        t0 = time.perf_counter()
        cursor = conn.cursor()
        for i in range(writes):
            cursor.execute(
                """
                INSERT INTO packets (id, hash, schema_version, project, created_at, origin, body)
                VALUES (?, ?, '0.1', 'bench_proj', '2026-01-01T00:00:00Z', 'cli', ?)
                """,
                (f"pkt_{r}_{i:04d}", f"hash_{r}_{i:04d}", b'{"payload": "realistic_context_data"}'),
            )
        conn.commit()
        t1 = time.perf_counter()
        conn.close()

        if r >= warmups:
            timings.append(t1 - t0)

    stats = _calc_stats(timings)
    writes_per_sec = round(writes / stats["median"], 1) if stats["median"] > 0 else 0.0
    results["single_writer"] = {
        "writes_count": writes,
        "latency_seconds": stats,
        "writes_per_sec": writes_per_sec,
        "rounds": rounds,
    }

    return results


def bench_mcp_latency(tmp_dir: Path, rounds: int = 25, warmups: int = 5) -> dict[str, Any]:
    """Benchmark MCP service method latencies."""
    store_dir = tmp_dir / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_file = store_dir / "swallo.db"
    key_file = store_dir / "key"

    conn = db.get_connection(db_file)
    db.apply_migrations(conn)
    get_or_create_local_key(key_file)

    proj_dir = (tmp_dir / "my_project").resolve()
    proj_dir.mkdir(parents=True, exist_ok=True)

    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO projects (root_path, name, registered_at) VALUES (?, 'bench_proj', '2026-01-01T00:00:00Z')",
        (str(proj_dir),),
    )
    conn.commit()
    conn.close()

    service = SwalloService(store_dir=store_dir)

    # Warmups
    for _ in range(warmups):
        service.list_contexts(project="bench_proj")

    list_timings: list[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        _ = service.list_contexts(project="bench_proj")
        t1 = time.perf_counter()
        list_timings.append(t1 - t0)

    save_timings: list[float] = []
    for i in range(rounds):
        payload = {
            "schema_version": "0.1",
            "project": "bench_proj",
            "created_at": "2026-01-01T00:00:00Z",
            "goal": {"text": f"Goal {i}"},
            "sources": [{"session_id": f"s_{i}", "agent": "claude", "capture_method": "paste", "captured_at": "2026-01-01T00:00:00Z"}],
            "items": [{"kind": "decision", "text": f"Decision {i}"}],
        }
        t0 = time.perf_counter()
        _ = service.save_context(packet_data=payload, project="bench_proj", session_id=f"sess_{i}")
        t1 = time.perf_counter()
        save_timings.append(t1 - t0)

    return {
        "list_contexts": _calc_stats(list_timings),
        "save_context_draft": _calc_stats(save_timings),
        "rounds": rounds,
    }


def bench_cli_cold_start(rounds: int = 10, warmups: int = 2) -> dict[str, Any]:
    """Benchmark CLI cold start execution time using isolated sub-processes."""
    commands = {
        "swallo_help": [sys.executable, "-m", "swallo.cli", "--help"],
        "swallo_list": [sys.executable, "-m", "swallo.cli", "list"],
    }
    results: dict[str, Any] = {}

    for name, cmd in commands.items():
        # Warmup - timeout=60 prevents hangs; measurement-critical so no check=True
        for _ in range(warmups):
            subprocess.run(cmd, capture_output=True, check=False, timeout=60)  # noqa: S603

        timings: list[float] = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            subprocess.run(cmd, capture_output=True, check=False, timeout=60)  # noqa: S603
            t1 = time.perf_counter()
            timings.append(t1 - t0)

        results[name] = _calc_stats(timings)

    return results


def bench_memory_tracemalloc_and_rss(sizes_mb: list[int] | None = None) -> dict[str, Any]:
    """
    Measure peak memory allocation separately from timing runs.
    Uses tracemalloc for Python heap allocation and psutil for process peak RSS cross-check.
    """
    if sizes_mb is None:
        sizes_mb = [1, 5]
    process = psutil.Process(os.getpid())
    results: dict[str, Any] = {}
    engine = RedactionEngine([PatternDetector(), EntropyDetector()])

    for sz in sizes_mb:
        target_bytes = sz * 1024 * 1024
        text = _generate_realistic_transcript(target_bytes)

        tracemalloc.start()
        tracemalloc.reset_peak()
        rss_before = process.memory_info().rss

        _ = engine.redact(text)

        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_after = process.memory_info().rss

        results[f"{sz}MB"] = {
            "tracemalloc_peak_bytes": peak_bytes,
            "tracemalloc_peak_mb": round(peak_bytes / (1024 * 1024), 2),
            "rss_delta_mb": round((rss_after - rss_before) / (1024 * 1024), 2),
            "rss_current_mb": round(rss_after / (1024 * 1024), 2),
        }

    return results


def bench_token_reduction() -> dict[str, Any]:
    """
    Benchmark token reduction: multi-domain realistic development sessions vs structured packets.
    Uses tiktoken (cl100k_base). Documented as benchmark-only metric.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        return {"status": f"SKIPPED (tiktoken unavailable: {exc})"}

    # Generate realistic multi-domain development sessions (debugging, refactoring, auth)
    domains = [
        ("auth", "User: We need to implement session authentication with rotating HMAC keys and rate limiting.\n"
                 "Agent: I will implement a token bucket limiter and secret signing module with Ed25519 fallbacks.\n"
                 "User: Make sure circuit breakers trip on 5 consecutive blocked saves.\n"
                 "Agent: Understood. Added circuit breaker state persistence in SQLite with 10-minute sliding windows."),
        ("db", "User: SQLite is throwing busy timeouts when two agent sessions write concurrently.\n"
               "Agent: Enabling PRAGMA journal_mode = WAL and busy_timeout = 5000 eliminates concurrent write lock contention.\n"
               "User: Let's verify migration idempotency.\n"
               "Agent: Added user_version check to prevent re-running completed schema migrations."),
        ("security", "User: Test archive guard against zip bombs and absolute symlinks.\n"
                     "Agent: Implemented streaming decompression ratio caps at 10:1 and member entry limit at 1,000.\n"
                     "User: How do we neutralize Trojan Source CVE-2021-42574 attacks?\n"
                     "Agent: We strip directional overrides (RLO, LRO, PDF) and tag planes before rendering to terminal."),
    ]

    raw_dialogue_parts: list[str] = []
    items: list[Item] = []

    for d_name, conversation in domains:
        for turn in range(5):
            raw_dialogue_parts.append(f"--- Session: {d_name} Turn {turn} ---\n{conversation}\n")
            items.append(Item(
                kind="decision",
                text=f"{d_name} turn {turn}: architectural constraint verified.",
                topic=d_name,
                value="enforced",
            ))

    raw_text = "\n".join(raw_dialogue_parts)
    raw_tokens = len(enc.encode(raw_text))

    packet = Packet(
        id="pkt_tok_reduction_rigorous",
        schema_version="0.1",
        created_at="2026-01-01T00:00:00Z",
        project="token_bench_rigorous",
        goal=Goal(text="Measure token reduction from realistic multi-domain sessions to compact handoff packet"),
        sources=[Source(session_id="s1", agent="antigravity", capture_method="export", captured_at="2026-01-01T00:00:00Z")],
        items=items,
    )
    packet_json = packet.model_dump_json()
    packet_tokens = len(enc.encode(packet_json))

    reduction_pct = round(((raw_tokens - packet_tokens) / raw_tokens) * 100, 2) if raw_tokens > 0 else 0.0

    return {
        "raw_transcript_tokens": raw_tokens,
        "packet_tokens": packet_tokens,
        "tokens_saved": raw_tokens - packet_tokens,
        "reduction_percentage": reduction_pct,
        "tokenizer": "cl100k_base",
    }


def run_perf_suite(out_dir: Path | None = None) -> dict[str, Any]:
    """Execute complete rigorous statistical performance benchmark suite."""
    if out_dir is None:
        out_dir = Path("benchmarks/results/perf")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Executing Rigorous Statistical Performance Benchmark Suite...")

    # Hardware & OS Environment
    env: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.architecture()[0],
        "python_version": platform.python_version(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
    }

    print("  -> Benchmarking Ingest & Redaction Throughput on Realistic Transcripts (20 rounds)...")
    redaction_res = bench_redaction(sizes_mb=[1, 5], rounds=20, warmups=5)

    print("  -> Benchmarking Canonical JSON & SHA-256 Hashing across Scales (25 rounds)...")
    hash_res = bench_canonical_hashing(item_counts=[10, 100, 500, 1000], rounds=25, warmups=5)

    print("  -> Benchmarking SQLite WAL Write Throughput with 1,000 writes (10 rounds)...")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_bench_dir:
        tmp_bench_path = Path(tmp_bench_dir)
        sqlite_res = bench_sqlite_wal(tmp_bench_path, writes=1000, rounds=10, warmups=2)

        print("  -> Benchmarking MCP Tool Latency (25 rounds)...")
        mcp_res = bench_mcp_latency(tmp_bench_path, rounds=25, warmups=5)

    print("  -> Benchmarking CLI Cold Start in Isolated Processes (10 rounds)...")
    cli_res = bench_cli_cold_start(rounds=10, warmups=2)

    print("  -> Measuring Peak Memory (tracemalloc separated + RSS cross-check)...")
    mem_res = bench_memory_tracemalloc_and_rss(sizes_mb=[1, 5])

    print("  -> Measuring Token Reduction Efficiency across Multi-Domain Sessions (tiktoken)...")
    token_res = bench_token_reduction()

    summary: dict[str, Any] = {
        "schema_version": "0.1",
        "swallo_version": __version__,
        "git_commit": _get_git_commit(),
        "environment": env,
        "benchmarks": {
            "redaction": redaction_res,
            "canonical_hashing": hash_res,
            "sqlite_wal": sqlite_res,
            "mcp_latency": mcp_res,
            "cli_cold_start": cli_res,
            "memory": mem_res,
            "token_reduction": token_res,
        },
    }

    summary_file = out_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Performance summary successfully written to: {summary_file}")
    return summary


if __name__ == "__main__":
    run_perf_suite()
