"""
Unit and integration tests for git repository state capture and staleness detection (F18).

Per TRD.md section 9.1, IMPLEMENTATION_PLAN.md Step 7, and FINDINGS_REGISTER.md F18:
- Temp-repo tests for:
  - Non-git repo handling
  - Up-to-date repo state
  - Unrelated commits (must NOT trigger drift)
  - Modified referenced file (triggers critical drift)
  - Deleted referenced file
  - Renamed referenced file
  - Diverged commit (rebase / non-ancestor)
  - Valid and expiring acknowledgments in `stale_acks`
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from swallo.repo.gitstate import (
    compute_git_blob_hash,
    get_git_commit,
    get_repo_state,
    hash_git_object,
    is_ancestor,
    is_git_dirty,
    is_git_repository,
)
from swallo.repo.staleness import (
    DriftItem,
    DriftType,
    check_staleness,
    compute_drift_hash,
    is_ack_valid,
    record_stale_ack,
)
from swallo.schema.models import Goal, Packet, RepoState, Source
from swallo.store.db import MIGRATION_001_SQL

GIT_BIN = shutil.which("git")


def _git(args: list[str], cwd: Path) -> None:
    """Run git command in test repo with safe timeout."""
    assert GIT_BIN is not None, "git executable required for git tests"
    subprocess.run([GIT_BIN, *args], cwd=str(cwd), check=True, timeout=30)  # noqa: S603


def _init_test_git_repo(repo_dir: Path) -> None:
    """Initialize a git repo with dummy user config."""
    _git(["init"], repo_dir)
    _git(["config", "user.email", "test@swallo.local"], repo_dir)
    _git(["config", "user.name", "Swallo Tester"], repo_dir)


def _make_dummy_packet(repo_state: RepoState | None = None) -> Packet:
    return Packet(
        schema_version="0.1",
        project="test-proj",
        created_at="2026-11-06T12:00:00Z",
        sources=[
            Source(
                session_id="s1",
                agent="test_agent",
                capture_method="manual",
                captured_at="2026-11-06T12:00:00Z",
            )
        ],
        goal=Goal(text="Test staleness"),
        repo_state=repo_state,
    )


def _setup_test_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(MIGRATION_001_SQL)
    return conn


def test_blob_hash_parity(tmp_path: Path) -> None:
    content = b"hello swallo staleness testing\n"
    py_hash = compute_git_blob_hash(content)

    test_file = tmp_path / "hello.txt"
    test_file.write_bytes(content)

    if GIT_BIN:
        git_hash = hash_git_object(tmp_path, "hello.txt")
        assert git_hash == py_hash
    assert len(py_hash) == 40


def test_non_git_repo_behavior(tmp_path: Path) -> None:
    non_git = tmp_path / "plain_dir"
    non_git.mkdir()
    assert not is_git_repository(non_git)
    assert get_git_commit(non_git) is None
    assert not is_git_dirty(non_git)
    assert get_repo_state(non_git, ["foo.py"]) is None

    packet = _make_dummy_packet(
        RepoState(git_commit="a" * 40, dirty=False, files={"foo.py": "b" * 40})
    )
    report = check_staleness(packet, non_git)
    assert not report.is_stale
    assert not report.is_critical
    assert not report.is_git_repo


@pytest.mark.skipif(GIT_BIN is None, reason="git binary not installed")
def test_up_to_date_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_test_git_repo(repo)

    f1 = repo / "main.py"
    f1.write_text("print('hello')", encoding="utf-8")
    _git(["add", "main.py"], repo)
    _git(["commit", "-m", "initial commit"], repo)

    state = get_repo_state(repo, ["main.py"])
    assert state is not None
    assert len(state.git_commit) == 40
    assert not state.dirty
    assert "main.py" in state.files

    packet = _make_dummy_packet(state)
    report = check_staleness(packet, repo)
    assert not report.is_stale
    assert not report.is_critical
    assert len(report.drifts) == 0


@pytest.mark.skipif(GIT_BIN is None, reason="git binary not installed")
def test_unrelated_commit_does_not_trigger_drift(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_test_git_repo(repo)

    f1 = repo / "ref.py"
    f1.write_text("print('ref')", encoding="utf-8")
    _git(["add", "ref.py"], repo)
    _git(["commit", "-m", "first commit"], repo)

    state = get_repo_state(repo, ["ref.py"])
    assert state is not None
    packet = _make_dummy_packet(state)

    # Make unrelated commit modifying another file
    f2 = repo / "unrelated.txt"
    f2.write_text("unrelated doc update", encoding="utf-8")
    _git(["add", "unrelated.txt"], repo)
    _git(["commit", "-m", "unrelated commit"], repo)

    report = check_staleness(packet, repo)
    # Ancestor check succeeds, ref.py hash is unchanged -> clean!
    assert not report.is_stale
    assert not report.is_critical
    assert len(report.drifts) == 0


@pytest.mark.skipif(GIT_BIN is None, reason="git binary not installed")
def test_modified_and_deleted_referenced_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_test_git_repo(repo)

    f1 = repo / "target.py"
    f1.write_text("v1", encoding="utf-8")
    f2 = repo / "delete_me.py"
    f2.write_text("to be deleted", encoding="utf-8")

    _git(["add", "target.py", "delete_me.py"], repo)
    _git(["commit", "-m", "add files"], repo)

    state = get_repo_state(repo, ["target.py", "delete_me.py"])
    assert state is not None
    packet = _make_dummy_packet(state)

    # 1. Modify target.py
    f1.write_text("v2 modified", encoding="utf-8")
    # 2. Delete delete_me.py
    f2.unlink()

    report = check_staleness(packet, repo)
    assert report.is_stale
    assert report.is_critical
    assert len(report.drifts) == 2

    drift_map = {d.path: d.drift_type for d in report.drifts}
    assert drift_map["target.py"] == DriftType.MODIFIED
    assert drift_map["delete_me.py"] == DriftType.DELETED


@pytest.mark.skipif(GIT_BIN is None, reason="git binary not installed")
def test_diverged_commit_detection(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_test_git_repo(repo)

    f1 = repo / "init.txt"
    f1.write_text("init", encoding="utf-8")
    _git(["add", "init.txt"], repo)
    _git(["commit", "-m", "initial commit"], repo)

    # Commit on main
    f2 = repo / "f2.txt"
    f2.write_text("f2", encoding="utf-8")
    _git(["add", "f2.txt"], repo)
    _git(["commit", "-m", "commit 2"], repo)
    head_commit = get_git_commit(repo)
    assert head_commit is not None

    # Suppose a packet was generated on an orphaned/diverged commit hash
    diverged_fake_commit = "f" * 40
    packet = _make_dummy_packet(
        RepoState(git_commit=diverged_fake_commit, dirty=False, files={})
    )

    assert not is_ancestor(repo, diverged_fake_commit, head_commit)
    report = check_staleness(packet, repo)
    assert report.is_stale
    assert report.is_critical
    assert any(d.drift_type == DriftType.DIVERGED_COMMIT for d in report.drifts)


def test_acknowledgment_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = _setup_test_db(db_path)
    key_bytes = b"k" * 32

    packet_hash = "p" * 64
    head = "h" * 40
    drifts = [
        DriftItem(
            path="mod.py",
            drift_type=DriftType.MODIFIED,
            expected_hash="1",
            current_hash="2",
        )
    ]
    drift_hash = compute_drift_hash(drifts)

    # 1. No ack exists yet
    assert not is_ack_valid(conn, key_bytes, packet_hash, head, drift_hash)

    # 2. Record valid ack
    mac = record_stale_ack(conn, key_bytes, packet_hash, head, drift_hash)
    assert len(mac) == 64
    assert is_ack_valid(conn, key_bytes, packet_hash, head, drift_hash, ttl_seconds=3600)

    # 3. Mismatched drift hash
    assert not is_ack_valid(conn, key_bytes, packet_hash, head, "different_drift_hash")

    # 4. Tampered key
    assert not is_ack_valid(conn, b"wrong_key" * 4, packet_hash, head, drift_hash)

    # 5. Expired ack (simulate timestamp in the past)
    expired_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE stale_acks SET acked_at = ? WHERE packet_hash = ?",
        (expired_time, packet_hash),
    )
    cursor.close()

    # Even though MAC was originally valid, TTL expiry must reject it
    assert not is_ack_valid(conn, key_bytes, packet_hash, head, drift_hash, ttl_seconds=86400)
