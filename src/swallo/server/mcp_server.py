"""
Standard Model Context Protocol (MCP) server implementation for swallo.

Per TRD.md section 3, 7, 8, 11 and CLI_AND_MCP_SPEC.md section 3:
- Exposes 7 safe tools:
  1. save_context (stores unapproved T1 draft; limits, redaction, rate limit, quota, dedupe)
  2. load_context (approved packets only; CSPRNG fence; staleness check; project-scoped)
  3. get_context (alias for load_context matching documented MCP tools)
  4. verify_context (read-only integrity check; recomputes hash, verifies chain/ledger)
  5. merge_contexts (merges 1..N packets into unapproved draft with conflicts listed)
  6. diff (item-level comparison with provenance tiers)
  7. list_contexts (summary metadata only; never leaks stored content)
- Deliberately absent: NO approve tool (SR-06). Human approval happens strictly at TTY CLI.
- No arbitrary file reads, no raw transcript returns.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from swallo.adapters.chat import ChatAdapter
from swallo.adapters.registry import get_adapter, list_supported_targets, normalize_target
from swallo.config import Config, get_store_dir, load_config
from swallo.errors import (
    IntegrityError,
    NotApprovedError,
    RateLimitedError,
    RedactionBlockedError,
    UsageError,
    ValidationError,
)
from swallo.merge.resolve import merge_packets
from swallo.redact.decode import DecodedVariantDetector
from swallo.redact.denylist import DenylistDetector
from swallo.redact.engine import RedactionEngine
from swallo.redact.entropy import EntropyDetector
from swallo.redact.patterns import PatternDetector
from swallo.render.fence import wrap_in_fence
from swallo.repo.staleness import check_staleness
from swallo.schema.canonical import (
    canonicalize,
    derive_packet_id,
    packet_hash,
    parse_canonical_json,
)
from swallo.schema.models import Packet, Provenance, Source
from swallo.server.guards import (
    CircuitBreaker,
    DraftQuotaManager,
    RateLimiter,
    check_deduplication,
    enforce_stale_policy,
    verify_project_registered,
)
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event
from swallo.store.eventlog import verify as verify_eventlog
from swallo.store.ledger import is_approved
from swallo.store.objects import ObjectStore


def _safe_json_loads(data: bytes | str) -> dict[str, Any]:
    """Parse canonical JSON safely, translating decode errors into IntegrityError."""
    try:
        res = parse_canonical_json(data)
        if isinstance(res, dict):
            return res
        raise IntegrityError("Expected JSON object dictionary from stored body.")
    except Exception as err:
        raise IntegrityError(f"Corrupted packet body in store: {err}") from err


class SwalloService:
    """Core logic powering both the MCP server and direct programmatic usage."""

    def __init__(self, store_dir: Path | None = None, config: Config | None = None) -> None:
        self.store_dir = (store_dir or get_store_dir()).resolve()
        loaded_cfg, _ = load_config(self.store_dir)
        self.config: Config = config or loaded_cfg
        self.db_path = self.store_dir / "swallo.db"
        self.key_path = self.store_dir / "key"

        if not self.db_path.exists() or not self.key_path.exists():
            raise UsageError(
                f"Store at '{self.store_dir}' not initialized. Run 'swallo init' first."
            )

        self.key_bytes = get_or_create_local_key(self.key_path)
        self.rate_limiter = RateLimiter(
            burst=self.config.mcp.rate_burst,
            refill_per_hour=self.config.mcp.rate_refill_per_hour,
        )
        self.circuit_breaker = CircuitBreaker(
            threshold=self.config.redact.breaker_threshold,
            window_minutes=self.config.redact.breaker_window_minutes,
        )
        self.quota_mgr = DraftQuotaManager(
            quota_count=self.config.mcp.draft_quota_count,
            quota_bytes=self.config.mcp.draft_quota_bytes,
            ttl_days=self.config.mcp.draft_ttl_days,
        )
        self.object_store = ObjectStore(self.store_dir)

        # Initialize redaction detectors
        patterns = PatternDetector()
        entropy = EntropyDetector(threshold=4.3)
        denylist = DenylistDetector(self.config.redact.denylist)
        decoded = DecodedVariantDetector(inner_detectors=[patterns, entropy])
        self.redact_engine = RedactionEngine([patterns, entropy, denylist, decoded])

    def save_context(
        self,
        packet_data: dict[str, Any],
        project: str,
        agent: str = "ide_agent",
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Save an unapproved draft packet submitted by an IDE agent."""
        conn = get_connection(self.db_path)
        try:
            # 1. Verify project registration
            proj_name, _ = verify_project_registered(conn, project)

            # 2. Check circuit breaker
            self.circuit_breaker.check_active(conn, session_id)

            # 3. Purge expired drafts first to maintain TTL
            self.quota_mgr.purge_expired_drafts(conn, project=proj_name)

            # 4. Check & enforce schema validation
            try:
                packet = Packet.model_validate(packet_data)
            except Exception as e:
                raise ValidationError(f"Schema validation failed: {e}") from e

            # Assign origin agent source if missing
            if not packet.sources:
                now_str = datetime.now(UTC).isoformat()
                packet.sources.append(
                    Source(
                        session_id=session_id,
                        agent=agent,
                        capture_method="ide-agent",
                        captured_at=now_str,
                    )
                )

            # Ensure all items carry provenance
            for item in packet.items:
                item.provenance.append(
                    Provenance(
                        session_id=session_id,
                    )
                )

            packet_dict = packet.model_dump(exclude_none=True)

            # 5. Compute canonical hash for deduplication
            h = packet_hash(packet_dict)

            # 6. Idempotent Deduplication Check (F19)
            existing_id = check_deduplication(conn, proj_name, h)
            if existing_id:
                return {
                    "id": existing_id,
                    "hash": h,
                    "status": "deduplicated",
                    "redactions": 0,
                    "warnings": [
                        "Payload identical to existing draft; reused without budget drain."
                    ],
                }

            # 7. Check Rate Limit
            rate_res = self.rate_limiter.check_and_consume(conn, session_id, cost=1.0)
            if not rate_res.allowed:
                raise RateLimitedError(
                    f"Rate limit exceeded for session '{session_id}'. "
                    f"Retry after {rate_res.retry_after_seconds} seconds."
                )

            # 8. Redact Packet Content
            total_redactions = 0
            mode = self.config.redact.mode
            try:
                if packet_dict.get("goal") and isinstance(packet_dict["goal"], dict):
                    goal_text = packet_dict["goal"].get("text", "")
                    if goal_text:
                        r = self.redact_engine.redact(goal_text, mode=mode, key=self.key_bytes)
                        packet_dict["goal"]["text"] = r.text
                        total_redactions += r.redacted_count

                for item_dict in packet_dict.get("items", []):
                    if isinstance(item_dict, dict) and "text" in item_dict:
                        r = self.redact_engine.redact(
                            item_dict["text"], mode=mode, key=self.key_bytes
                        )
                        item_dict["text"] = r.text
                        total_redactions += r.redacted_count
            except RedactionBlockedError as e:
                self.circuit_breaker.record_blocked_save(conn, session_id)
                log_event(
                    conn,
                    self.key_bytes,
                    "blocked",
                    packet_hash=h,
                    detail=f"Save blocked for session '{session_id}': secrets detected",
                )
                raise RedactionBlockedError(
                    "Save blocked: confidential tokens detected in payload."
                ) from e

            # 9. Enforce Quotas
            canonical_bytes = canonicalize(packet_dict)
            self.quota_mgr.enforce_quotas(conn, proj_name, incoming_bytes=len(canonical_bytes))

            # 10. Persist Packet
            pkt_id = derive_packet_id(h)
            now = datetime.now(UTC)
            expires_at = (now + timedelta(days=self.config.mcp.draft_ttl_days)).isoformat()

            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO packets
                        (id, hash, schema_version, project, parent,
                         created_at, body, origin, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'mcp', ?)
                    """,
                    (
                        pkt_id,
                        h,
                        str(packet_dict.get("schema_version", "0.1")),
                        proj_name,
                        packet_dict.get("parent"),
                        str(packet_dict.get("created_at", now.isoformat())),
                        canonical_bytes,
                        expires_at,
                    ),
                )
            finally:
                cursor.close()

            self.object_store.put(canonical_bytes)
            log_event(
                conn,
                self.key_bytes,
                "saved",
                packet_hash=h,
                detail=f"mcp draft saved by {agent} (session: {session_id})",
            )

            return {
                "id": pkt_id,
                "hash": h,
                "status": "saved_draft",
                "redactions": total_redactions,
                "warnings": [],
            }
        finally:
            conn.close()

    def load_context(
        self,
        project: str,
        packet_id: str = "latest",
        target: str = "claude-code",
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Load an approved packet for delivery to the requesting IDE agent."""
        canonical_target = normalize_target(target)
        legacy_target = "claude_code" if canonical_target == "claude-code" else canonical_target
        conn = get_connection(self.db_path)
        try:
            proj_name, proj_root = verify_project_registered(conn, project)
            cursor = conn.cursor()
            try:
                if packet_id == "latest":
                    cursor.execute(
                        """
                        SELECT p.id, p.hash, p.body
                        FROM packets p
                        INNER JOIN approvals a ON p.hash = a.packet_hash
                        WHERE p.project = ? AND (a.target = ? OR a.target = ? OR a.target = 'all')
                        ORDER BY p.created_at DESC
                        LIMIT 1
                        """,
                        (proj_name, canonical_target, legacy_target),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, hash, body FROM packets
                        WHERE (id = ? OR hash = ?) AND project = ?
                        """,
                        (packet_id, packet_id, proj_name),
                    )
                row = cursor.fetchone()
            finally:
                cursor.close()

            if not row:
                raise UsageError(
                    f"No packet matching '{packet_id}' found for project '{proj_name}'."
                )

            pkt_id, pkt_hash, body = str(row[0]), str(row[1]), bytes(row[2])

            # Verify Approval
            if not is_approved(conn, self.key_bytes, pkt_hash, canonical_target):
                raise NotApprovedError(
                    f"Packet '{pkt_id}' is not approved for target '{canonical_target}'. "
                    "Human approval required via 'swallo approve' CLI."
                )

            packet_dict = _safe_json_loads(body)
            packet = Packet.model_validate(packet_dict)

            # Staleness and Drift Check
            report = check_staleness(packet, proj_root, conn, self.key_bytes)
            warnings = enforce_stale_policy(report, self.config.stale.policy_mcp)

            # Render through adapter
            adapter = get_adapter(canonical_target)
            chat_renderer = adapter if isinstance(adapter, ChatAdapter) else ChatAdapter()
            rendered_body = chat_renderer.render(
                packet_dict, token_budget=self.config.budget.default_tokens
            )

            # Fencing: wrap in CSPRNG fence with untrusted data header
            fenced_output, _ = wrap_in_fence(rendered_body, title=f"Swallo Packet {pkt_id}")

            log_event(
                conn,
                self.key_bytes,
                "served",
                packet_hash=pkt_hash,
                target=canonical_target,
                detail=f"mcp load_context served to session '{session_id}'",
            )

            return {
                "id": pkt_id,
                "hash": pkt_hash,
                "target": canonical_target,
                "content": fenced_output,
                "warnings": warnings,
            }
        finally:
            conn.close()

    def merge_contexts(
        self,
        ids: list[str],
        into: str,
        project: str,
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Merge multiple existing packets into a new unapproved draft with conflict list."""
        if len(ids) < 2:
            raise ValidationError("merge_contexts requires at least two packet IDs.")

        conn = get_connection(self.db_path)
        try:
            proj_name, _ = verify_project_registered(conn, project)
            self.circuit_breaker.check_active(conn, session_id)

            packet_dicts: list[dict[str, Any]] = []
            cursor = conn.cursor()
            try:
                for pid in ids:
                    cursor.execute(
                        "SELECT body FROM packets WHERE (id = ? OR hash = ?) AND project = ?",
                        (pid, pid, proj_name),
                    )
                    row = cursor.fetchone()
                    if not row:
                        raise UsageError(f"Packet '{pid}' not found in project '{proj_name}'.")
                    pkt_dict = _safe_json_loads(bytes(row[0]))
                    packet_dicts.append(pkt_dict)
            finally:
                cursor.close()

            merged_dict = merge_packets(packet_dicts, into=into)
            h = packet_hash(merged_dict)
            pkt_id = derive_packet_id(h)
            canonical_bytes = canonicalize(merged_dict)

            now = datetime.now(UTC)
            expires_at = (now + timedelta(days=self.config.mcp.draft_ttl_days)).isoformat()

            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO packets
                        (id, hash, schema_version, project, parent,
                         created_at, body, origin, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'mcp', ?)
                    """,
                    (
                        pkt_id,
                        h,
                        str(merged_dict.get("schema_version", "0.1")),
                        proj_name,
                        None,
                        str(merged_dict.get("created_at", now.isoformat())),
                        canonical_bytes,
                        expires_at,
                    ),
                )
            finally:
                cursor.close()

            self.object_store.put(canonical_bytes)
            log_event(
                conn,
                self.key_bytes,
                "merged",
                packet_hash=h,
                detail=f"merged {len(ids)} packets via mcp by session '{session_id}'",
            )

            conflicts_list = merged_dict.get("conflicts", [])
            return {
                "id": pkt_id,
                "hash": h,
                "status": "merged_draft",
                "conflicts": conflicts_list,
            }
        finally:
            conn.close()

    def diff(self, a: str, b: str, project: str) -> dict[str, Any]:
        """Item-level structural diff of two packets with provenance tiers."""
        conn = get_connection(self.db_path)
        try:
            proj_name, _ = verify_project_registered(conn, project)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT id, hash, body FROM packets WHERE (id = ? OR hash = ?) AND project = ?",
                    (a, a, proj_name),
                )
                row_a = cursor.fetchone()
                cursor.execute(
                    "SELECT id, hash, body FROM packets WHERE (id = ? OR hash = ?) AND project = ?",
                    (b, b, proj_name),
                )
                row_b = cursor.fetchone()
            finally:
                cursor.close()

            if not row_a:
                raise UsageError(f"Packet '{a}' not found.")
            if not row_b:
                raise UsageError(f"Packet '{b}' not found.")

            pkt_a = Packet.model_validate(_safe_json_loads(bytes(row_a[2])))
            pkt_b = Packet.model_validate(_safe_json_loads(bytes(row_b[2])))

            items_a = {it.id or it.text: it for it in pkt_a.items}
            items_b = {it.id or it.text: it for it in pkt_b.items}

            added: list[dict[str, Any]] = [
                {
                    "id": it.id,
                    "kind": it.kind,
                    "text": it.text,
                }
                for k, it in items_b.items()
                if k not in items_a
            ]
            removed: list[dict[str, Any]] = [
                {
                    "id": it.id,
                    "kind": it.kind,
                    "text": it.text,
                }
                for k, it in items_a.items()
                if k not in items_b
            ]
            common: list[dict[str, Any]] = [
                {
                    "id": it.id,
                    "kind": it.kind,
                    "text": it.text,
                }
                for k, it in items_b.items()
                if k in items_a
            ]

            return {
                "packet_a": {"id": row_a[0], "hash": row_a[1]},
                "packet_b": {"id": row_b[0], "hash": row_b[1]},
                "added_items": added,
                "removed_items": removed,
                "shared_items": common,
            }
        finally:
            conn.close()

    def get_context(
        self,
        project: str,
        packet_id: str = "latest",
        target: str = "claude-code",
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Low-risk alias for load_context matching documented MCP tools."""
        return self.load_context(
            project=project,
            packet_id=packet_id,
            target=target,
            session_id=session_id,
        )

    def verify_context(self, project: str, packet_id: str) -> dict[str, Any]:
        """
        Read-only verification tool: recompute hash, verify event chain, check ledger approvals.
        Returns a structured report. Never returns plaintext secrets or content body.
        """
        conn = get_connection(self.db_path)
        try:
            proj_name, _ = verify_project_registered(conn, project)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT id, hash, body
                    FROM packets
                    WHERE (id = ? OR hash = ?) AND project = ?
                    """,
                    (packet_id, packet_id, proj_name),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()

            if not row:
                raise UsageError(f"Packet '{packet_id}' not found in project '{proj_name}'.")

            pkt_id, pkt_hash, body_raw = str(row[0]), str(row[1]), row[2]

            # Recompute content hash from stored body
            hash_verified = False
            computed_h = None
            try:
                body_dict = parse_canonical_json(body_raw)
                if isinstance(body_dict, dict):
                    computed_h = packet_hash(body_dict)
                    hash_verified = (computed_h == pkt_hash)
            except Exception:
                hash_verified = False

            # Verify eventlog HMAC chain
            event_errors = verify_eventlog(conn, self.key_bytes)
            event_chain_ok = len(event_errors) == 0

            # Check approval status across supported targets
            supported_targets = list_supported_targets()
            approvals = {
                tgt: is_approved(conn, self.key_bytes, pkt_hash, tgt)
                for tgt in supported_targets
            }

            return {
                "packet_id": pkt_id,
                "project": proj_name,
                "stored_hash": pkt_hash,
                "computed_hash": computed_h,
                "hash_verified": hash_verified,
                "event_chain_ok": event_chain_ok,
                "event_errors": event_errors,
                "approvals": approvals,
            }
        finally:
            conn.close()

    def list_contexts(self, project: str, state: str = "all") -> list[dict[str, Any]]:
        """List summary metadata for packets in project (never returns content)."""
        conn = get_connection(self.db_path)
        try:
            proj_name, _ = verify_project_registered(conn, project)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT p.id, p.hash, p.created_at, p.origin, p.expires_at,
                           (SELECT COUNT(*) FROM approvals a
                            WHERE a.packet_hash = p.hash) AS app_count
                    FROM packets p
                    WHERE p.project = ?
                    ORDER BY p.created_at DESC
                    """,
                    (proj_name,),
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

            results: list[dict[str, Any]] = []
            for r in rows:
                pkt_id, pkt_h, created_at, origin, expires_at, app_count = r
                is_app = int(app_count) > 0
                pkt_state = "approved" if is_app else "draft"
                if state != "all" and pkt_state != state:
                    continue
                results.append(
                    {
                        "id": pkt_id,
                        "hash": pkt_h,
                        "created_at": created_at,
                        "origin": origin,
                        "state": pkt_state,
                        "expires_at": expires_at,
                    }
                )
            return results
        finally:
            conn.close()


def create_mcp_server(service: SwalloService | None = None) -> object:
    """Create FastMCP server instance registering the 7 safe tools."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise UsageError(
            "The official MCP SDK is required to run the server. "
            "Install with: pip install 'swallo[mcp]'"
        ) from e

    svc = service or SwalloService()
    mcp_app = FastMCP(
        "swallo",
        instructions="Secure handoff server for AI agents. Deliberately provides no approval tool.",
    )

    @mcp_app.tool()
    def save_context(
        packet: dict[str, Any],
        project: str,
        agent: str = "ide_agent",
        session_id: str = "default",
    ) -> str:
        """Store an unapproved draft packet (tier T1). Limits and redaction apply."""
        res = svc.save_context(packet, project=project, agent=agent, session_id=session_id)
        return json.dumps(res, indent=2)

    @mcp_app.tool()
    def load_context(
        project: str,
        id: str = "latest",
        target: str = "claude-code",
        session_id: str = "default",
    ) -> str:
        """Load an approved packet for delivery to target IDE. Fenced against injection."""
        res = svc.load_context(
            project=project,
            packet_id=id,
            target=target,
            session_id=session_id,
        )
        return json.dumps(res, indent=2)

    @mcp_app.tool()
    def get_context(
        project: str,
        id: str = "latest",
        target: str = "claude-code",
        session_id: str = "default",
    ) -> str:
        """Alias for load_context matching documented MCP tools. Fenced against injection."""
        res = svc.get_context(
            project=project,
            packet_id=id,
            target=target,
            session_id=session_id,
        )
        return json.dumps(res, indent=2)

    @mcp_app.tool()
    def verify_context(
        project: str,
        id: str,
    ) -> str:
        """Verify integrity: recompute hash, verify event chain, check ledger approvals."""
        res = svc.verify_context(project=project, packet_id=id)
        return json.dumps(res, indent=2)

    @mcp_app.tool()
    def merge_contexts(
        ids: list[str],
        into: str,
        project: str,
        session_id: str = "default",
    ) -> str:
        """Merge 1..N packets into a new unapproved draft with conflict detection."""
        res = svc.merge_contexts(ids=ids, into=into, project=project, session_id=session_id)
        return json.dumps(res, indent=2)

    @mcp_app.tool()
    def diff(a: str, b: str, project: str) -> str:
        """Compare two packets item-by-item with provenance tiers."""
        res = svc.diff(a=a, b=b, project=project)
        return json.dumps(res, indent=2)

    @mcp_app.tool()
    def list_contexts(project: str, state: str = "all") -> str:
        """List summary metadata for packets in project (metadata only, no content)."""
        res = svc.list_contexts(project=project, state=state)
        return json.dumps(res, indent=2)

    return mcp_app
