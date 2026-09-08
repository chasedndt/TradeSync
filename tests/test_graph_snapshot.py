"""A ChaseOS snapshot is evidence. It is never permission, and never partial."""

from __future__ import annotations

import copy

import pytest

from tradesync_core.graph_snapshot import (
    FORBIDDEN_FIELDS,
    SnapshotRejected,
    snapshot_digest,
    summarise,
    validate_snapshot,
)


def node(node_id: str, **over):
    base = {
        "node_id": node_id,
        "label": node_id.replace("_", " "),
        "node_type": "doc_section",
        "source_file": "02_KNOWLEDGE/regimes.md",
        "source_line": 12,
        "domain": "aor",
        "project": None,
        "properties": {},
        "confidence": "EXTRACTED",
        "provenance": "markdown:heading",
    }
    base.update(over)
    return base


def edge(edge_id: str, source: str, target: str, **over):
    base = {
        "edge_id": edge_id,
        "source_id": source,
        "target_id": target,
        "relation": "references",
        "confidence": "EXTRACTED",
        "properties": {},
        "provenance": "markdown:wikilink",
    }
    base.update(over)
    return base


def snapshot(**over):
    base = {
        "snapshot_id": "snap-001",
        "created_at": "2026-09-08T12:00:00Z",
        "vault_root": r"C:\Users\chaseos\Documents\chaseos_chaseintech",
        "extraction_scope": ["02_KNOWLEDGE"],
        "nodes": [node("n_a"), node("n_b")],
        "edges": [edge("e_ab", "n_a", "n_b")],
        "community_assignments": {"n_a": 0, "n_b": 0},
        "build_info": {"extractor_version": "1.0", "elapsed_ms": 812},
        "metadata": {},
    }
    base.update(over)
    return base


def test_a_well_formed_snapshot_is_accepted_and_normalised() -> None:
    result = validate_snapshot(snapshot())
    assert result["snapshot_id"] == "snap-001"
    assert [n["node_id"] for n in result["nodes"]] == ["n_a", "n_b"]
    assert result["edges"][0]["relation"] == "references"
    assert result["content_digest"]


@pytest.mark.parametrize("field", sorted(FORBIDDEN_FIELDS))
def test_a_node_claiming_authority_is_refused_by_name(field: str) -> None:
    """Refused, not stripped.

    Silently removing the field would accept a connector that tried to grant
    itself scoring or approval authority and leave no trace of the attempt.
    """
    doc = snapshot(nodes=[node("n_a", properties={field: True}), node("n_b")])
    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot(doc)
    assert field in str(excinfo.value)
    assert "never permission" in str(excinfo.value)


@pytest.mark.parametrize("field", sorted(FORBIDDEN_FIELDS))
def test_an_edge_claiming_authority_is_refused_by_name(field: str) -> None:
    doc = snapshot(edges=[edge("e_ab", "n_a", "n_b", properties={field: "yes"})])
    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot(doc)
    assert field in str(excinfo.value)


def test_an_edge_to_a_node_not_in_the_snapshot_is_refused() -> None:
    """A recursive adjacency query would walk straight off it.

    The result would be a path through a node this snapshot never described,
    returned with the same confidence as a real one.
    """
    doc = snapshot(edges=[edge("e_ax", "n_a", "n_missing")])
    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot(doc)
    assert "n_missing" in str(excinfo.value)


def test_duplicate_ids_are_refused() -> None:
    """Ids are content-derived and stable by contract.

    A duplicate means the extraction was not deterministic, and projecting it
    would pick an arbitrary winner.
    """
    with pytest.raises(SnapshotRejected):
        validate_snapshot(snapshot(nodes=[node("n_a"), node("n_a")]))
    with pytest.raises(SnapshotRejected):
        validate_snapshot(
            snapshot(edges=[edge("e_ab", "n_a", "n_b"), edge("e_ab", "n_b", "n_a")])
        )


def test_an_unknown_confidence_marker_is_refused() -> None:
    """The vocabulary is ChaseOS's; inventing a value is a contract break."""
    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot(snapshot(nodes=[node("n_a", confidence="TRUSTED"), node("n_b")]))
    assert "TRUSTED" in str(excinfo.value)

    with pytest.raises(SnapshotRejected):
        validate_snapshot(snapshot(edges=[edge("e_ab", "n_a", "n_b", confidence="")]))


def test_missing_required_fields_are_named() -> None:
    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot({"nodes": [], "edges": []})
    assert "snapshot_id" in str(excinfo.value)

    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot(snapshot(nodes=[{"node_id": "n_a"}], edges=[]))
    assert "label" in str(excinfo.value)


def test_a_snapshot_without_node_and_edge_arrays_is_refused() -> None:
    doc = snapshot()
    del doc["edges"]
    with pytest.raises(SnapshotRejected):
        validate_snapshot(doc)


def test_community_assignments_naming_unknown_nodes_are_refused() -> None:
    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot(snapshot(community_assignments={"n_ghost": 3}))
    assert "n_ghost" in str(excinfo.value)


def test_an_empty_graph_is_valid() -> None:
    """A vault with nothing extracted yet is a fact, not an error."""
    result = validate_snapshot(snapshot(nodes=[], edges=[], community_assignments={}))
    assert result["nodes"] == []
    assert summarise(result)["nodes"] == 0


def test_the_digest_ignores_build_timings_and_free_form_metadata() -> None:
    """Otherwise every rebuild of an unchanged corpus looks like new knowledge."""
    first = snapshot()
    second = snapshot(
        build_info={"extractor_version": "1.0", "elapsed_ms": 9999},
        metadata={"note": "re-run after lunch"},
    )
    assert snapshot_digest(first) == snapshot_digest(second)


def test_the_digest_moves_when_the_graph_actually_changes() -> None:
    before = snapshot()
    after = copy.deepcopy(before)
    after["nodes"].append(node("n_c"))
    assert snapshot_digest(before) != snapshot_digest(after)

    reordered = copy.deepcopy(before)
    reordered["nodes"] = list(reversed(reordered["nodes"]))
    # Order is not content: the same graph written in a different order is the
    # same graph.
    assert snapshot_digest(before) == snapshot_digest(reordered)


def test_the_summary_states_that_the_projection_is_not_canonical() -> None:
    result = validate_snapshot(
        snapshot(
            nodes=[node("n_a"), node("n_b", node_type="file", confidence="INFERRED")],
            edges=[edge("e_ab", "n_a", "n_b", relation="file_contains")],
        )
    )
    summary = summarise(result)
    assert summary["authority"] == "read_only_projection"
    assert summary["nodes_by_type"] == {"doc_section": 1, "file": 1}
    assert summary["nodes_by_confidence"] == {"EXTRACTED": 1, "INFERRED": 1}
    assert summary["edges_by_relation"] == {"file_contains": 1}


def test_a_malformed_created_at_is_a_stated_refusal_not_a_server_error() -> None:
    """It used to be checked at projection time, outside the 422 handling.

    A snapshot with an unparseable timestamp escaped the endpoint as a bare
    500. It is a contract violation like any other and belongs with them, so the
    operator gets a reason they can take back to ChaseOS.
    """
    with pytest.raises(SnapshotRejected) as excinfo:
        validate_snapshot(snapshot(created_at="last Tuesday"))
    assert "ISO 8601" in str(excinfo.value)


def test_iso_timestamps_with_and_without_a_trailing_z_are_both_accepted() -> None:
    for stamp in ("2026-09-08T12:00:00Z", "2026-09-08T12:00:00+00:00", "2026-09-08T12:00:00"):
        assert validate_snapshot(snapshot(created_at=stamp))["created_at"] == stamp


def test_the_creation_time_is_never_replaced_with_now() -> None:
    """Dating a snapshot to when TradeSync read it is not when it was extracted."""
    from tradesync_core.graph_snapshot import parse_created_at

    parsed = parse_created_at("2020-01-02T03:04:05Z")
    assert (parsed.year, parsed.month, parsed.day) == (2020, 1, 2)


def test_the_digest_ignores_the_snapshot_id() -> None:
    """ChaseOS mints a fresh id per extraction run.

    Including it would move the digest on every rebuild regardless of whether
    the corpus changed, which is exactly the question the digest answers.
    """
    assert snapshot_digest(snapshot(snapshot_id="run-a")) == snapshot_digest(
        snapshot(snapshot_id="run-b")
    )


def test_the_digest_still_separates_different_vaults() -> None:
    """Same note ids extracted from a different root are not the same graph."""
    assert snapshot_digest(snapshot()) != snapshot_digest(
        snapshot(vault_root=r"C:\somewhere\else")
    )


def test_the_shared_parser_reports_unparseable_naive_text_as_a_refusal() -> None:
    """A naive-looking string that is not a timestamp at all.

    It takes the allow-naive branch, where a bare ValueError from
    fromisoformat would escape past every caller that catches TimestampError
    and surface as a server error rather than a stated refusal.
    """
    from tradesync_core.timeparse import TimestampError, parse_utc_allow_naive

    with pytest.raises(TimestampError):
        parse_utc_allow_naive("last Tuesday", "created_at")
    # A genuinely naive ISO timestamp is still accepted by this variant.
    assert parse_utc_allow_naive("2026-09-08T12:00:00").hour == 12
