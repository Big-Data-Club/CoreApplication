"""Pure regression tests for graph node budgeting and orphan compaction."""

from app.services.auto_index_service import (
    AutoIndexService,
    ExtractedNode,
    ExtractedRelation,
    MAX_NODES_PER_DOCUMENT,
)
from app.services.chunker import DocumentChunk
from app.services.graph_consolidation_service import ConsolidationPlan, MergeGroup


def _node(index: int, evidence_count: int = 1) -> ExtractedNode:
    return ExtractedNode(
        name=f"Concept {index}",
        name_vi=f"Khái niệm {index}",
        name_en=f"Concept {index}",
        description=(f"Grounded description for concept {index}. " * 5),
        keywords=[f"k{index}"],
        order_index=index,
        evidence_chunk_indexes=list(range(index, index + evidence_count)),
    )


def test_document_node_budget_caps_and_reindexes_relations():
    chunks = [
        DocumentChunk(text="x" * 400, index=i, source_type="document")
        for i in range(60)
    ]
    nodes = [_node(i, evidence_count=2 if i >= 10 else 1) for i in range(20)]
    relations = [
        ExtractedRelation(i, i + 1, "related", "adjacent")
        for i in range(19)
    ]

    kept_nodes, kept_relations = AutoIndexService._limit_document_nodes(
        nodes, relations, chunks,
    )

    assert len(kept_nodes) == MAX_NODES_PER_DOCUMENT
    assert all(0 <= r.source_index < len(kept_nodes) for r in kept_relations)
    assert all(0 <= r.target_index < len(kept_nodes) for r in kept_relations)
    # Concepts with broader cited evidence outrank one-chunk fragments.
    assert {n.order_index for n in kept_nodes}.issuperset(set(range(10, 20)))


def test_excluding_orphan_keeps_node_vector_and_relation_indexes_aligned():
    nodes = [_node(i) for i in range(3)]
    ids = [101, 102, 103]
    vectors = [[1.0], [2.0], [3.0]]
    relations = [
        ExtractedRelation(0, 1, "related", "drop"),
        ExtractedRelation(0, 2, "prerequisite", "keep"),
    ]

    kept_nodes, kept_relations, kept_ids, kept_vectors = AutoIndexService._exclude_nodes(
        nodes, relations, ids, vectors, {102},
    )

    assert [n.order_index for n in kept_nodes] == [0, 2]
    assert kept_ids == [101, 103]
    assert kept_vectors == [[1.0], [3.0]]
    assert [(r.source_index, r.target_index) for r in kept_relations] == [(0, 1)]


def test_consolidation_totals_include_orphan_deletion():
    group = MergeGroup(
        survivor_id=1,
        absorbed_ids=[2, 3],
        new_name="Concept",
        new_name_vi="Khái niệm",
        new_description="Description",
    )
    plan = ConsolidationPlan(
        course_id=7,
        groups=[group],
        total_nodes_before=10,
        orphaned_ids=[8, 9, 10],
        orphaned_names={8: "A", 9: "B", 10: "C"},
    )

    payload = plan.to_dict()
    assert plan.total_nodes_after == 5
    assert payload["orphaned_count"] == 3
    assert payload["total_nodes_after"] == 5

