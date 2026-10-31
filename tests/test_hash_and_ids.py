"""
Property tests for hashed form, packet hash, and derived IDs.
"""

from __future__ import annotations

import unicodedata

from hypothesis import given
from hypothesis import strategies as st

from swallo.schema.canonical import (
    derive_item_id,
    derive_packet_id,
    hashed_form,
    packet_hash,
)


def _sample_packet() -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "id": "pkt_sample12345",
        "created_at": "2026-10-31T12:00:00Z",
        "project": "test-project",
        "parent": None,
        "merged_from": [],
        "sources": [
            {
                "session_id": "s1",
                "agent": "chatgpt",
                "capture_method": "paste",
                "captured_at": "2026-10-31T11:59:00Z",
                "transcript": {"object": "sha256:1234567890abcdef", "redacted": True},
            }
        ],
        "goal": {"text": "Build swallo test suite"},
        "items": [
            {
                "id": "it_12345678",
                "kind": "decision",
                "text": "Use hypothesis for property testing",
                "critical": False,
                "provenance": [{"session_id": "s1", "span": None}],
            }
        ],
        "conflicts": [],
    }


def test_hashed_form_excludes_volatile_fields() -> None:
    pkt = _sample_packet()
    h_form = hashed_form(pkt)

    assert "id" not in h_form
    assert "created_at" not in h_form
    assert "project" in h_form
    assert "goal" in h_form

    sources = h_form["sources"]
    assert isinstance(sources, list)
    assert len(sources) == 1
    assert "captured_at" not in sources[0]
    assert sources[0]["session_id"] == "s1"


def test_packet_hash_volatile_invariance() -> None:
    pkt1 = _sample_packet()
    pkt2 = _sample_packet()

    # Alter volatile fields
    pkt2["id"] = "pkt_different_id"
    pkt2["created_at"] = "2026-12-01T00:00:00Z"
    sources2 = pkt2["sources"]
    assert isinstance(sources2, list)
    sources2[0]["captured_at"] = "2026-12-01T00:00:00Z"

    assert packet_hash(pkt1) == packet_hash(pkt2)


def test_packet_hash_content_sensitivity() -> None:
    pkt1 = _sample_packet()
    pkt2 = _sample_packet()

    pkt2["project"] = "different-project"
    assert packet_hash(pkt1) != packet_hash(pkt2)

    pkt3 = _sample_packet()
    items = pkt3["items"]
    assert isinstance(items, list)
    items[0]["text"] = "Changed decision text"
    assert packet_hash(pkt1) != packet_hash(pkt3)


def test_derive_packet_id_and_collision_extension() -> None:
    pkt = _sample_packet()
    p_hash = packet_hash(pkt)
    raw_hex = p_hash.removeprefix("sha256:")

    id1 = derive_packet_id(p_hash)
    assert id1 == f"pkt_{raw_hex[:12]}"

    # Collision test: first 12 chars already taken
    taken = {id1}
    id2 = derive_packet_id(p_hash, taken=taken)
    assert id2 == f"pkt_{raw_hex[:14]}"
    assert len(id2) == 18  # "pkt_" (4) + 14 hex


def test_derive_item_id_nfc_consistency() -> None:
    # Combining accent (NFD) vs precomposed (NFC)
    text_nfd = "cafe\u0301"
    text_nfc = "café"

    assert text_nfd != text_nfc
    id_nfd = derive_item_id("decision", text_nfd)
    id_nfc = derive_item_id("decision", text_nfc)

    assert id_nfd == id_nfc
    assert id_nfd.startswith("it_")
    assert len(id_nfd) == 11  # "it_" (3) + 8 hex


def test_derive_item_id_collision_extension() -> None:
    id1 = derive_item_id("decision", "Ship feature A")
    taken = {id1}
    id2 = derive_item_id("decision", "Ship feature A", taken=taken)

    assert id2 != id1
    assert id2.startswith(id1)
    assert len(id2) == len(id1) + 2


@given(
    kind=st.sampled_from(["decision", "constraint", "question", "artifact_ref"]),
    text=st.text(min_size=1),
)
def test_derive_item_id_property(kind: str, text: str) -> None:
    nfd = unicodedata.normalize("NFD", text)
    nfc = unicodedata.normalize("NFC", text)

    id_nfd = derive_item_id(kind, nfd)
    id_nfc = derive_item_id(kind, nfc)

    assert id_nfd == id_nfc
    assert id_nfd.startswith("it_")
