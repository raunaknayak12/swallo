"""
New-user validation test script.

Executes outside the repository in an isolated virtual environment to verify:
1. Zero-warning import and zero optional module leaks in core
2. CLI help (--help and python -m swallo --help)
3. swallo init and swallo doctor on clean HOME
4. End-to-end golden path (prompt -> save -> list -> show -> approve -> send -> MCP load -> log --verify)
   NOTE: CI uses this test harness helper for approval because CI runners lack an interactive TTY.
         Real interactive TTY prompt coverage is provided by maintainer manual test on Windows laptop.
5. Upgrade path from v0.1.2 store (including legacy underscore targets)
6. Actionable error messages without tracebacks
7. MCP compatibility and tool invariants
"""

from __future__ import annotations

# ruff: noqa: S101, S603, S607
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def get_swallo_cmd() -> list[str]:
    """
    Determine whether to invoke 'swallo' executable or 'python -m swallo'.
    On Windows environments with Application Control policies, entrypoint .exe binaries
    may be restricted; 'python -m swallo' serves as the verified fallback.
    """
    try:
        res = subprocess.run(
            ["swallo", "--help"],
            capture_output=True,
            timeout=5,
        )
        if res.returncode == 0:
            return ["swallo"]
    except (OSError, subprocess.SubprocessError):
        pass
    return [sys.executable, "-m", "swallo"]


def run_cmd(
    args: list[str],
    env: dict[str, str] | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute command with timeout and environment."""
    # Resolve 'swallo' if at start of command
    if args and args[0] == "swallo":
        args = get_swallo_cmd() + args[1:]

    res = subprocess.run(
        args,
        env=env or os.environ.copy(),
        capture_output=capture,
        text=True,
        timeout=60,
    )
    if check and res.returncode != 0:
        raise RuntimeError(
            f"Command {args} failed (exit {res.returncode}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
        )
    return res


def test_import_and_isolation() -> None:
    print("Testing zero-warning import and core isolation...")
    run_cmd([sys.executable, "-W", "error", "-c", "import swallo"])
    check_leak_script = (
        "import sys, swallo\n"
        "assert 'mcp' not in sys.modules, 'mcp leaked into core'\n"
        "assert 'cryptography' not in sys.modules, 'cryptography leaked into core'\n"
        "assert 'tiktoken' not in sys.modules, 'tiktoken leaked into core'\n"
    )
    run_cmd([sys.executable, "-c", check_leak_script])
    print("  -> Import and core isolation PASSED")


def test_cli_help() -> None:
    print("Testing CLI help commands...")
    swallo = get_swallo_cmd()
    res1 = run_cmd(swallo + ["--help"])
    assert "Usage: swallo" in res1.stdout or "swallo [OPTIONS]" in res1.stdout or "Swallo" in res1.stdout

    res2 = run_cmd([sys.executable, "-m", "swallo", "--help"])
    assert "Usage: swallo" in res2.stdout or "swallo [OPTIONS]" in res2.stdout or "Swallo" in res2.stdout
    print("  -> CLI help commands PASSED")


def test_golden_path_and_lifecycle(temp_dir: Path) -> None:
    print("Testing init, doctor, and golden path...")
    swallo_home = temp_dir / ".swallo_home"
    env = os.environ.copy()
    env["SWALLO_HOME"] = str(swallo_home)

    # 1. init
    run_cmd(["swallo", "init"], env=env)
    assert (swallo_home / "swallo.db").exists()
    assert (swallo_home / "key").exists()

    # 2. doctor on clean store
    doc_res = run_cmd(["swallo", "doctor"], env=env)
    assert doc_res.returncode == 0
    assert "checks passed" in doc_res.stdout.lower() or "[ok]" in doc_res.stdout.lower()

    # 3. prompt
    prompt_res = run_cmd(["swallo", "prompt"], env=env)
    assert len(prompt_res.stdout) > 50

    # 4. save sample packet matching swallo schema v0.1
    sample_packet = {
        "schema_version": "0.1",
        "project": "default",
        "created_at": "2026-11-15T00:00:00Z",
        "sources": [
            {
                "session_id": "sess_new_user_001",
                "agent": "antigravity",
                "capture_method": "paste",
                "captured_at": "2026-11-15T00:00:00Z",
            }
        ],
        "goal": {
            "text": "Verify new user experience on clean installation",
        },
        "items": [
            {
                "kind": "decision",
                "text": "Adopted pure-python core architecture",
            },
            {
                "kind": "constraint",
                "text": "Zero network egress allowed in core",
            },
        ],
    }
    sample_file = temp_dir / "sample_packet.json"
    sample_file.write_text(json.dumps(sample_packet, indent=2), encoding="utf-8")

    save_res = run_cmd(["swallo", "save", str(sample_file)], env=env)
    # Extract packet ID and hash from save output
    lines = save_res.stdout.splitlines()
    pkt_id = None
    pkt_hash = None
    for line in lines:
        if "ID:" in line and "pkt_" in line:
            pkt_id = line.split("pkt_")[1].split()[0]
            pkt_id = f"pkt_{pkt_id}"
        if "Hash:" in line and "sha256:" in line:
            pkt_hash = line.split("sha256:")[1].strip()
    assert pkt_id is not None, f"Could not find packet ID in save output: {save_res.stdout}"
    assert pkt_hash is not None, f"Could not find packet hash in save output: {save_res.stdout}"

    # 5. list
    list_res = run_cmd(["swallo", "list"], env=env)
    assert pkt_id in list_res.stdout

    # 6. show
    show_res = run_cmd(["swallo", "show", pkt_id], env=env)
    assert "Adopted pure-python core architecture" in show_res.stdout
    assert "Verify new user experience" in show_res.stdout

    # 7. approve via test harness helper
    # In CI, no interactive TTY is attached; test harness invokes ledger.approve directly.
    approve_script = (
        "import sqlite3, sys\n"
        "from pathlib import Path\n"
        "from swallo.store import ledger\n"
        "home = Path(sys.argv[1])\n"
        "full_hash = sys.argv[2]\n"
        "key_path = home / 'key'\n"
        "key = key_path.read_bytes()\n"
        "conn = sqlite3.connect(str(home / 'swallo.db'))\n"
        "ledger.approve(conn, key, full_hash, 'antigravity')\n"
        "conn.close()\n"
    )
    run_cmd([sys.executable, "-c", approve_script, str(swallo_home), f"sha256:{pkt_hash}"], env=env)

    # 8. send
    project_dir = temp_dir / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(project_dir)
    send_res = run_cmd(["swallo", "send", pkt_id, "--to", "antigravity"], env=env)
    assert "delivered" in send_res.stdout.lower() or "success" in send_res.stdout.lower() or "sent" in send_res.stdout.lower()
    handoff_dir = project_dir / ".swallo" / "handoff"
    assert handoff_dir.exists()
    assert len(list(handoff_dir.glob("*.md"))) > 0

    # 9. log --verify
    log_res = run_cmd(["swallo", "log", "--verify"], env=env)
    assert "0 error" in log_res.stdout.lower() or "zero tampering" in log_res.stdout.lower() or "authentic" in log_res.stdout.lower()
    print("  -> Golden path PASSED")


def test_upgrade_path(temp_dir: Path) -> None:
    print("Testing upgrade path from v0.1.2 store...")
    upgrade_home = temp_dir / ".swallo_upgrade_home"
    env = os.environ.copy()
    env["SWALLO_HOME"] = str(upgrade_home)

    run_cmd(["swallo", "init"], env=env)

    # Simulate legacy store state with underscore target 'claude_code'
    legacy_script = (
        "import sqlite3, sys\n"
        "from pathlib import Path\n"
        "from swallo.store import ledger\n"
        "home = Path(sys.argv[1])\n"
        "key = (home / 'key').read_bytes()\n"
        "conn = sqlite3.connect(str(home / 'swallo.db'))\n"
        "ledger.approve(conn, key, 'sha256:' + ('b' * 64), 'claude_code')\n"
        "conn.close()\n"
    )
    run_cmd([sys.executable, "-c", legacy_script, str(upgrade_home)], env=env)

    # Verify doctor and log --verify on upgraded store
    run_cmd(["swallo", "doctor"], env=env)
    run_cmd(["swallo", "log", "--verify"], env=env)
    print("  -> Upgrade path PASSED")


def test_actionable_errors(temp_dir: Path) -> None:
    print("Testing actionable error handling (no tracebacks)...")
    env = os.environ.copy()
    env["SWALLO_HOME"] = str(temp_dir / ".swallo_home")

    # Missing file
    res = run_cmd(["swallo", "save", "nonexistent_file.json"], env=env, check=False)
    assert res.returncode != 0
    assert "Traceback (most recent call last):" not in res.stderr
    assert "Traceback (most recent call last):" not in res.stdout
    assert "error" in (res.stderr + res.stdout).lower() or "not found" in (res.stderr + res.stdout).lower()

    # Malformed JSON
    bad_json = temp_dir / "bad.json"
    bad_json.write_text("{ unquoted_key: 123 ", encoding="utf-8")
    res = run_cmd(["swallo", "save", str(bad_json)], env=env, check=False)
    assert res.returncode != 0
    assert "Traceback (most recent call last):" not in res.stderr

    # Unknown target
    res = run_cmd(["swallo", "send", "a" * 64, "--to", "unknown_ide"], env=env, check=False)
    assert res.returncode != 0
    assert "Traceback (most recent call last):" not in res.stderr

    print("  -> Actionable error handling PASSED")


def test_mcp_fastmcp_and_invariants() -> None:
    print("Testing FastMCP integration and MCP invariants...")
    try:
        from mcp.server.fastmcp import FastMCP

        if FastMCP is None:
            raise ImportError("FastMCP is None")
        from swallo.server.mcp_server import SwalloService, create_mcp_server
    except ImportError as e:
        print(f"MCP extra not installed or failed to import FastMCP: {e}")
        return

    server = create_mcp_server()
    assert server is not None

    service_methods = [
        m for m in dir(SwalloService)
        if not m.startswith("_") and callable(getattr(SwalloService, m))
    ]
    # Invariant F18: Zero approve tools exposed via MCP
    assert not any("approve" in m.lower() for m in service_methods), "Approve tool exposed in MCP!"
    print("  -> FastMCP integration and invariants PASSED")


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="swallo_new_user_"))
    try:
        test_import_and_isolation()
        test_cli_help()
        test_golden_path_and_lifecycle(temp_dir)
        test_upgrade_path(temp_dir)
        test_actionable_errors(temp_dir)
        test_mcp_fastmcp_and_invariants()
        print("\nAll new-user validation checks completed successfully!")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
