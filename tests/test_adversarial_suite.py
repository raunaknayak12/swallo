"""
Comprehensive seeded adversarial testbed for Swallo security invariants (Phase 4).

Tests cover realistic attack classes across:
1. Secrets detection & redaction across encodings
2. Trojan Source (CVE-2021-42574) and invisible characters
3. Prompt injection payloads & structural enclosure invariants
4. Terminal escape / ANSI injection in show and status/list outputs
5. Archive attacks (zip-slip, deeply nested JSON recursion, size quotas)
6. Path traversal, SQL characters, long strings, NUL bytes
7. ReDoS resistance on regex detectors with strict timeout
8. Concurrency & HMAC ledger chain integrity under parallel writers
9. Store tamper detection (log --verify and doctor)
10. Clobber tests for target files written by swallo send
"""

from __future__ import annotations

import concurrent.futures
import json
import time
import zipfile
from pathlib import Path

import pytest

from scripts.generate_adversarial_fixtures import (
    ANSI_ESCAPE_PAYLOAD,
    PROMPT_INJECTION_DIRECT,
    PROMPT_INJECTION_FENCE_BREAKOUT,
    SYNTHETIC_AWS_KEY,
    SYNTHETIC_GITHUB_TOKEN,
    TROJAN_BIDI_PAYLOAD,
    TROJAN_TAG_PAYLOAD,
    TROJAN_ZERO_WIDTH_PAYLOAD,
    generate_adversarial_project,
    generate_nested_json,
    generate_zip_slip_archive,
)
from swallo.adapters.base import update_marker_block
from swallo.capture.importers.base import ArchiveGuard
from swallo.capture.importers.stream import safe_json_loads
from swallo.commands import doctor as cmd_doctor
from swallo.commands import init as cmd_init
from swallo.commands import log as cmd_log
from swallo.commands import save as cmd_save
from swallo.commands import show as cmd_show
from swallo.commands import status as cmd_status
from swallo.config import ImporterSettings
from swallo.errors import RedactionBlockedError, SecurityError, UsageError, ValidationError
from swallo.redact.engine import RedactionEngine
from swallo.redact.patterns import PatternDetector
from swallo.render.fence import wrap_in_fence
from swallo.render.sanitize import flag_invisible, sanitize_for_display
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.ledger import approve as ledger_approve
from swallo.store.ledger import is_approved

# ==============================================================================
# 1. Secrets Detection & Redaction
# ==============================================================================

def test_secrets_detection_and_fail_closed(tmp_path: Path) -> None:
    """Verify secrets in plain and encoded forms are detected and blocked fail-closed."""
    proj = generate_adversarial_project(tmp_path / "adversarial_proj")

    # Engine with pattern detector
    engine = RedactionEngine([PatternDetector()])

    # 1. Plain secret in fail-closed mode should raise RedactionBlockedError
    env_text = proj["env"].read_text(encoding="utf-8")
    with pytest.raises(RedactionBlockedError, match="Redaction blocked save"):
        engine.redact(env_text, mode="fail_closed")

    # 2. Engine in warn mode replaces with placeholders
    res = engine.redact(env_text, mode="warn")
    assert SYNTHETIC_AWS_KEY not in res.text
    assert SYNTHETIC_GITHUB_TOKEN not in res.text
    assert "[REDACTED:" in res.text
    assert len(res.findings) >= 2


# ==============================================================================
# 2. Trojan Source (CVE-2021-42574) & Invisible Characters
# ==============================================================================

def test_trojan_source_bidi_and_invisible_character_handling() -> None:
    """Verify Trojan Source bidi controls are stripped and invisible chars are flagged."""
    # BiDi overrides must be stripped by sanitize_for_display
    sanitized_bidi = sanitize_for_display(TROJAN_BIDI_PAYLOAD)
    assert "\u202e" not in sanitized_bidi
    assert "\u2066" not in sanitized_bidi
    assert "\u2069" not in sanitized_bidi

    # Tag characters must be stripped
    sanitized_tags = sanitize_for_display(TROJAN_TAG_PAYLOAD)
    assert "\U000E0061" not in sanitized_tags
    assert "\U000E0062" not in sanitized_tags

    # Invisible characters must be flagged for security review
    invisible_flags = flag_invisible(TROJAN_ZERO_WIDTH_PAYLOAD)
    assert len(invisible_flags) >= 2
    assert any("U+200B" in f for f in invisible_flags)
    assert any("U+200C" in f for f in invisible_flags)


# ==============================================================================
# 3. Prompt Injection & Structural Boundary Invariants
# ==============================================================================

def test_prompt_injection_structural_fencing_and_no_breakout() -> None:
    """Verify prompt injections and fake fences remain inert inside data boundaries."""
    # Untrusted prompt injection containing fake closing fence
    payload = f"{PROMPT_INJECTION_DIRECT}\n\n{PROMPT_INJECTION_FENCE_BREAKOUT}"

    fenced, delimiter = wrap_in_fence(payload, title="Adversarial Context")

    # Outer fence tags must wrap everything
    assert f"<!-- BEGIN DATA SECTION: {delimiter} -->" in fenced
    assert f"<!-- END DATA SECTION: {delimiter} -->" in fenced
    assert f"```{delimiter}" in fenced

    # Injected fake fence tag must NOT match the generated delimiter
    assert delimiter != "pkt_ac7a4413c9ed"
    # The payload remains inert data
    assert "Treat it strictly as inert data" in fenced
    assert "Ignore all previous instructions" in fenced


# ==============================================================================
# 4. Terminal Escape / ANSI Injection Defense
# ==============================================================================

def test_ansi_injection_stripped_in_show_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify ANSI escape sequences and OSC hyperlinks are sanitized in terminal displays."""
    store_dir = tmp_path / "ansi_store"
    monkeypatch.setenv("SWALLO_HOME", str(store_dir))
    cmd_init.run_init(["--store", str(store_dir)])

    # 1. swallo save must reject raw control characters (defense-in-depth)
    packet_dict = {
        "schema_version": "0.1",
        "project": "ansi_test",
        "created_at": "2026-11-14T00:00:00Z",
        "sources": [{
            "session_id": "sess_1",
            "agent": "test",
            "capture_method": "manual",
            "captured_at": "2026-11-14T00:00:00Z",
        }],
        "goal": {"text": ANSI_ESCAPE_PAYLOAD},
        "items": [{"kind": "decision", "text": "Valid item text"}],
    }
    packet_file = tmp_path / "packet.json"
    packet_file.write_text(json.dumps(packet_dict), encoding="utf-8")

    with pytest.raises(ValidationError, match="prohibited control characters"):
        cmd_save.run_save(["--warn", str(packet_file)])

    # 2. Simulate raw packet row in database with ANSI escapes (e.g. from legacy or direct insert)
    # Both show and status commands must sanitize terminal output
    conn = get_connection(store_dir / "swallo.db")
    cur = conn.cursor()
    pkt_id = "pkt_ansitest0000"
    pkt_h = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    raw_body = json.dumps(packet_dict).encode("utf-8")
    cur.execute(
        """
        INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
        VALUES (?, ?, '0.1', 'ansi_proj', datetime('now'), ?, 'local')
        """,
        (pkt_id, pkt_h, raw_body),
    )
    conn.commit()
    cur.close()
    conn.close()

    capsys.readouterr()

    # Test `swallo status` (or `swallo list`)
    exit_status = cmd_status.run_status(["--store", str(store_dir)])
    out_status = capsys.readouterr().out
    assert exit_status == 0
    # ANSI escape characters must NOT be present in terminal output
    assert "\x1b[" not in out_status
    assert "\x1b]" not in out_status

    # Test `swallo show`
    exit_show = cmd_show.run_show([pkt_id, "--store", str(store_dir)])
    out_show = capsys.readouterr().out
    assert exit_show == 0
    assert "\x1b[" not in out_show
    assert "\x1b]" not in out_show


# ==============================================================================
# 5. Archive & Decompression Attacks
# ==============================================================================

def test_archive_attacks_rejected(tmp_path: Path) -> None:
    """Verify zip-slip and deeply nested JSON attacks are detected and rejected."""
    guard = ArchiveGuard(ImporterSettings())

    # 1. Zip slip archive
    zip_bytes = generate_zip_slip_archive()
    zip_file = tmp_path / "slip.zip"
    zip_file.write_bytes(zip_bytes)

    with zipfile.ZipFile(zip_file, "r") as zf:
        with pytest.raises(SecurityError, match="Path traversal detected in archive entry"):
            guard.verify_zip_structure(zf)

    # 2. Deeply nested JSON recursion attack
    nested_json = generate_nested_json(depth=80)
    with pytest.raises(SecurityError, match="exceeds maximum permitted limit"):
        safe_json_loads(nested_json, max_depth=50)


# ==============================================================================
# 6. Path Traversal & Injection in CLI Arguments
# ==============================================================================

def test_cli_path_traversal_and_sql_injection_defense(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify path traversal in packet IDs and SQL special chars do not escape or inject."""
    store_dir = tmp_path / "traversal_store"
    monkeypatch.setenv("SWALLO_HOME", str(store_dir))
    cmd_init.run_init(["--store", str(store_dir)])

    # 1. Packet ID with path traversal
    with pytest.raises((UsageError, ValidationError)):
        cmd_show.run_show(["../../etc/passwd", "--store", str(store_dir)])

    # 2. Packet ID with SQL injection payload
    with pytest.raises((UsageError, ValidationError)):
        cmd_show.run_show(["' OR '1'='1' --", "--store", str(store_dir)])

    # 3. Packet ID with NUL byte
    with pytest.raises((UsageError, ValidationError, ValueError)):
        cmd_show.run_show(["pkt_123\x00extra", "--store", str(store_dir)])


# ==============================================================================
# 7. ReDoS Resistance on Redaction Regexes
# ==============================================================================

def test_redos_pattern_adversarial_timeout() -> None:
    """Verify redaction patterns resist catastrophic backtracking on adversarial input."""
    engine = RedactionEngine([PatternDetector()])

    # Generate adversarial inputs: repeated quotes, alternating characters, long runs of spaces
    adversarial_inputs = [
        "Bearer " + "a" * 10000 + "!",
        "sk_live_" + ("0123456789" * 1000) + "_test",
        "ghp_" + ("A" * 10000),
        "postgres://" + ("user:" * 500) + "@localhost:5432/db",
        "-----BEGIN RSA PRIVATE KEY-----" + ("\n" * 1000),
        "   " * 5000 + "key=val",
    ]

    for attack_str in adversarial_inputs:
        start = time.perf_counter()
        # Scan with timeout guarantee
        res = engine.redact(attack_str, mode="warn")
        elapsed = time.perf_counter() - start
        # ReDoS would take seconds to hours; must finish in < 0.5 seconds
        assert elapsed < 0.5, f"Potential ReDoS detected: took {elapsed:.2f}s on input"
        assert isinstance(res.text, str)


@pytest.mark.parametrize(
    ("pattern_name", "adversarial_payload"),
    [
        ("aws_access_key", "AKIA" + "0" * 5000 + "!"),
        ("github_token", "ghp_" + "a" * 5000 + "@"),
        ("openai_api_key", "sk-proj-" + "x" * 5000 + "%"),
        ("anthropic_api_key", "sk-ant-" + "z" * 5000 + "^"),
        ("slack_token", "xoxb-" + "9" * 5000 + "*"),
        ("private_key", "-----BEGIN PRIVATE KEY-----" + "A" * 5000),
        ("bearer_token", "Bearer " + "token-part-" * 1000),
        ("connection_password", 'password="' + "a" * 5000),
    ],
)
def test_redos_per_pattern_exhaustive(pattern_name: str, adversarial_payload: str) -> None:
    """Explicitly verify each individual secret regex pattern against pathological inputs."""
    from swallo.redact.patterns import _SECRET_PATTERNS

    pattern_dict = dict(_SECRET_PATTERNS)
    assert pattern_name in pattern_dict, f"Missing pattern: {pattern_name}"
    regex = pattern_dict[pattern_name]

    start = time.perf_counter()
    regex.search(adversarial_payload)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"ReDoS vulnerability in {pattern_name}: took {elapsed:.3f}s"


# ==============================================================================
# 8. Concurrency & HMAC Ledger Chain Integrity
# ==============================================================================

def test_concurrency_and_ledger_hmac_integrity(tmp_path: Path) -> None:
    """Verify concurrent approvals preserve HMAC chain and valid signatures."""
    store_dir = tmp_path / "concurrent_store"
    cmd_init.run_init(["--store", str(store_dir)])
    db_path = store_dir / "swallo.db"

    # Pre-generate key
    key_bytes = get_or_create_local_key(store_dir / "key")

    def record_worker(worker_id: int) -> bool:
        thread_conn = get_connection(db_path)
        try:
            for j in range(5):
                packet_hash = f"hash_{worker_id}_{j}"
                ledger_approve(thread_conn, key_bytes, packet_hash, "claude-code")
            return True
        finally:
            thread_conn.close()

    # Run 5 concurrent worker threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(record_worker, i) for i in range(5)]
        results = [f.result(timeout=10) for f in futures]
    assert all(results)

    # Verify each recorded approval is verified successfully by HMAC
    verify_conn = get_connection(db_path)
    try:
        cur = verify_conn.cursor()
        cur.execute("SELECT packet_hash, target FROM approvals")
        rows = cur.fetchall()
        assert len(rows) == 25
        for ph, tgt in rows:
            assert is_approved(verify_conn, key_bytes, str(ph), str(tgt))
    finally:
        verify_conn.close()


def test_concurrency_kill_mid_write_integrity(tmp_path: Path) -> None:
    """Verify store integrity when a writer process is abruptly killed mid-write."""
    import subprocess
    import sys

    store_dir = tmp_path / "kill_store"
    cmd_init.run_init(["--store", str(store_dir)])
    db_path = store_dir / "swallo.db"

    # Spawn a Python process that rapidly records events and writes to the store
    worker_script = f"""
import sys, time
from pathlib import Path
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.ledger import approve

store = Path(r"{store_dir}")
conn = get_connection(store / "swallo.db")
key = get_or_create_local_key(store / "key")

for i in range(1000):
    approve(conn, key, f"hash_{{i}}", "claude-code")
    time.sleep(0.002)
"""
    # Run the worker script with a hard timeout of 0.1s.
    # subprocess.run automatically sends SIGKILL/TerminateProcess on timeout expiration.
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(  # noqa: S603 - spawning isolated local test script with current sys.executable
            [sys.executable, "-c", worker_script],
            capture_output=True,
            timeout=0.1,
            check=False,
        )

    # Database must remain intact, WAL recovery must succeed, and log must be clean
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        status = cur.fetchone()[0]
        assert status == "ok", f"Integrity check failed after kill: {status}"
    finally:
        conn.close()

    # Doctor check on store must pass
    exit_doc = cmd_doctor.run_doctor(["--store", str(store_dir)])
    assert exit_doc == 0


# ==============================================================================
# 9. Store Tamper Detection
# ==============================================================================

def test_store_tamper_detection_in_log_and_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify log, doctor, status, and ledger detect deliberate tampering of database tables."""
    store_dir = tmp_path / "tamper_store"
    monkeypatch.setenv("SWALLO_HOME", str(store_dir))
    cmd_init.run_init(["--store", str(store_dir)])
    db_path = store_dir / "swallo.db"
    key_bytes = get_or_create_local_key(store_dir / "key")

    # Save a legitimate packet
    packet_dict = {
        "schema_version": "0.1",
        "project": "tamper_demo",
        "created_at": "2026-11-14T00:00:00Z",
        "sources": [{
            "session_id": "sess_legit",
            "agent": "test",
            "capture_method": "manual",
            "captured_at": "2026-11-14T00:00:00Z",
        }],
        "goal": {"text": "Tamper test goal"},
        "items": [],
    }
    packet_file = tmp_path / "legit.json"
    packet_file.write_text(json.dumps(packet_dict), encoding="utf-8")
    cmd_save.run_save(["--warn", str(packet_file)])
    capsys.readouterr()

    # Pre-tampering: log --verify must succeed
    exit_log_clean = cmd_log.run_log(["--verify"])
    assert exit_log_clean == 0
    capsys.readouterr()

    # Pre-tampering: doctor must report all OK
    exit_doctor_clean = cmd_doctor.run_doctor(["--store", str(store_dir)])
    assert exit_doctor_clean == 0
    capsys.readouterr()

    # 1. Tamper with eventlog HMAC chain in SQLite database
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE events SET detail = 'tampered' WHERE seq = 1")
    conn.commit()
    cur.close()
    conn.close()

    # Post-tampering: log --verify must detect chain violation and exit non-zero
    exit_log_tampered = cmd_log.run_log(["--verify"])
    assert exit_log_tampered != 0
    capsys.readouterr()

    # Post-tampering: doctor must report FAIL on event_log_integrity
    exit_doctor_tampered = cmd_doctor.run_doctor(["--store", str(store_dir)])
    out_doctor = capsys.readouterr().out
    assert exit_doctor_tampered != 0
    assert "event_log_integrity" in out_doctor and "FAIL" in out_doctor

    # 2. Tamper with packet body in SQLite database
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE packets SET body = ? WHERE project = ?",
        (b"not_valid_json_corrupted{{{", "tamper_demo"),
    )
    conn.commit()
    cur.close()
    conn.close()

    # Post-tampering: swallo status must flag row as <corrupt> and return non-zero
    exit_status = cmd_status.run_status(["--store", str(store_dir)])
    out_status = capsys.readouterr().out
    assert exit_status != 0
    assert "<corrupt>" in out_status

    # 3. Tamper with approvals MAC
    conn = get_connection(db_path)
    fake_hash = "fake_pkt_hash_00000000000000000000000000000000000000000000000000000000"
    ledger_approve(conn, key_bytes, fake_hash, "claude-code")
    assert is_approved(conn, key_bytes, fake_hash, "claude-code") is True

    # Mutate MAC in database
    cur = conn.cursor()
    cur.execute(
        "UPDATE approvals SET mac = 'forged_mac_0000000000000000' WHERE packet_hash = ?",
        (fake_hash,),
    )
    conn.commit()
    cur.close()

    # Verify is_approved now rejects the forged approval
    assert is_approved(conn, key_bytes, fake_hash, "claude-code") is False
    conn.close()


# ==============================================================================
# 10. Clobber Tests for File Delivery
# ==============================================================================

def test_clobber_protection_and_idempotence(tmp_path: Path) -> None:
    """Verify swallo send preserves pre-existing content and updates marker cleanly."""
    target_file = tmp_path / "CLAUDE.md"
    initial_content = (
        "# Custom User Instructions\n\n"
        "Do not touch my custom workflows.\n"
        "Keep this line intact at all costs.\n"
    )
    target_file.write_text(initial_content, encoding="utf-8")

    nonce_marker = "pkt_ac7a4413c9ed"
    begin_marker = f"<!-- swallo:begin {nonce_marker} -->"
    end_marker = f"<!-- swallo:end {nonce_marker} -->"
    block_content = "Context delivered by Swallo v0.1.3\n"

    # 1. First update
    updated_1 = update_marker_block(initial_content, begin_marker, end_marker, block_content)
    target_file.write_text(updated_1, encoding="utf-8")
    first_read = target_file.read_text(encoding="utf-8")

    assert "Do not touch my custom workflows." in first_read
    assert begin_marker in first_read
    assert block_content in first_read
    assert end_marker in first_read

    # 2. Second update with updated payload (idempotent block replacement)
    updated_block = "Updated context delivered by Swallo v0.1.3\n"
    updated_2 = update_marker_block(first_read, begin_marker, end_marker, updated_block)
    target_file.write_text(updated_2, encoding="utf-8")
    second_read = target_file.read_text(encoding="utf-8")

    assert "Do not touch my custom workflows." in second_read
    assert second_read.count(begin_marker) == 1
    assert second_read.count(end_marker) == 1
    assert updated_block in second_read
    assert block_content not in second_read
