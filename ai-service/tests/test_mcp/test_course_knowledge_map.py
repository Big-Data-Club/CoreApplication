from __future__ import annotations

import pytest

from app.agents.tools.teacher.mcp_course_knowledge import (
    McpCourseKnowledgeReadTool,
    McpSaveCourseKnowledgeTool,
    _plan_nodes,
    embedding_text,
    prepare_edges,
    prepare_nodes,
    prerequisite_cycle,
)


def _node(**overrides):
    node = {"key": "m1-cache", "name": "KV cache"}
    node.update(overrides)
    return node


def test_prepare_nodes_defaults_order_and_validates_content_scope():
    nodes = prepare_nodes([_node(source_content_id=11)], {11})
    assert nodes[0]["order_index"] == 0
    assert nodes[0]["source_content_id"] == 11
    with pytest.raises(ValueError):
        prepare_nodes([_node(source_content_id=99)], {11})


def test_prepare_nodes_rejects_duplicate_names_and_bad_keys():
    with pytest.raises(ValueError):
        prepare_nodes([_node(), _node(key="m2", name="  kv   CACHE ")])
    with pytest.raises(ValueError):
        prepare_nodes([_node(key="KV Cache")])


def test_prepare_edges_defaults_and_validation():
    edges = prepare_edges([{"source_key": "a", "target_key": "b"}], {"a", "b"})
    assert edges == [{"source_key": "a", "target_key": "b",
                      "relation_type": "prerequisite", "strength": 1.0}]
    with pytest.raises(ValueError):
        prepare_edges([{"source_key": "a", "target_key": "missing"}], {"a"})
    with pytest.raises(ValueError):
        prepare_edges([{"source_key": "a", "target_key": "a"}], {"a"})
    with pytest.raises(ValueError):
        prepare_edges([{"source_key": "a", "target_key": "b", "strength": 2}], {"a", "b"})


def test_prerequisite_cycle_detects_direct_and_transitive_cycles():
    assert prerequisite_cycle([("b", "a")], [("a", "b")]) == [("b", "a")]
    assert prerequisite_cycle([("c", "a")], [("a", "b"), ("b", "c")]) == [("c", "a")]
    assert prerequisite_cycle([("a", "c")], [("a", "b"), ("b", "c")]) == []


def test_plan_reuses_matching_teacher_node_without_overwriting():
    by_name = {"kv cache": {"id": 7, "name": "KV cache", "level": 0, "external_key": None, "managed_by": None}}
    plan, reused, warnings = _plan_nodes([_node()], {}, by_name)
    assert plan["m1-cache"]["action"] == "reuse"
    assert plan["m1-cache"]["id"] == 7
    assert reused == {"m1-cache"}
    assert warnings


def test_plan_updates_agent_row_and_sets_hierarchy_levels():
    by_key = {
        "m1-cache": {"id": 3, "name": "KV cache", "level": 0, "external_key": "m1-cache",
                     "managed_by": "mcp-knowledge-map"},
        "m1-attention": {"id": 4, "name": "Attention", "level": 0,
                         "external_key": "m1-attention", "managed_by": "mcp-knowledge-map"},
    }
    nodes = [_node(key="m1-cache", parent_key="m1-attention"), _node(key="m1-attention", name="Attention")]
    plan, reused, _ = _plan_nodes(nodes, by_key, {})
    assert plan["m1-cache"]["action"] == "update"
    assert plan["m1-cache"]["level"] == 1
    assert not reused
    assert plan["m1-attention"]["level"] == 0


def test_plan_rejects_parent_cycle():
    with pytest.raises(ValueError):
        _plan_nodes(
            [_node(key="a", name="A", parent_key="b"), _node(key="b", name="B", parent_key="a")],
            {}, {},
        )


def test_embedding_text_includes_objectives_and_misconceptions():
    nodes = prepare_nodes([_node(objectives=["Explain eviction"],
                                 misconceptions=["Cache is permanent"])])
    text = embedding_text(nodes[0])
    assert "KV cache" in text
    assert "Explain eviction" in text
    assert "Cache is permanent" in text


@pytest.mark.asyncio
async def test_save_requires_explicit_confirmation():
    result = await McpSaveCourseKnowledgeTool().execute(
        _user_id=5, course_id=1, confirmed=False, nodes=[_node()],
    )
    assert result.status == "error"
    assert result.data["error"] == "confirmation_required"


@pytest.mark.asyncio
async def test_read_rejects_unknown_action_without_network():
    result = await McpCourseKnowledgeReadTool().execute(
        _user_id=5, course_id=1, action="everything",
    )
    assert result.status == "error"
    assert result.data["error"] == "invalid_action"
