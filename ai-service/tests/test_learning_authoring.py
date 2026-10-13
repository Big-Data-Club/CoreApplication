"""Offline regressions for curriculum scope, evidence and semantic planning."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import learning_context as context_module
from app.services import learning_design as design_module
from app.services.learning_context import AuthoringSource, LearningContext, build_learning_context
from app.services.learning_design import plan_learning_units
from app.services.quiz_service import QuizGenerationService


def connection(results):
    conn = AsyncMock()
    conn.fetch.side_effect = results
    manager = AsyncMock()
    manager.__aenter__.return_value = conn
    return conn, manager


def test_text_lesson_works_before_node_extraction():
    conn, manager = connection([[], []])
    source = AuthoringSource(content_id=9, title="Stacks", type="TEXT", text="Stacks use last-in-first-out ordering.")
    with patch.object(context_module, "get_ai_conn", return_value=manager):
        context = asyncio.run(build_learning_context(2, [source, source]))
    assert len(context.sources) == 1
    assert context.sources[0]["text"] == source.text
    assert context.node_ids == []
    assert conn.fetch.await_args_list[0].args[1:] == (2, [9])


def test_parent_context_and_unassigned_chunks_survive_without_duplication():
    chunks = [
        {"id": 1, "content_id": 9, "node_id": 10, "chunk_index": 0, "evidence_id": 20, "text": "Definition plus complete worked example."},
        {"id": 2, "content_id": 9, "node_id": 11, "chunk_index": 1, "evidence_id": 20, "text": "Definition plus complete worked example."},
        {"id": 3, "content_id": 9, "node_id": None, "chunk_index": 2, "evidence_id": 3, "text": "![Figure](/files/figure.png)"},
    ]
    relations = [{"source_node_id": 10, "target_node_id": 11, "relation_type": "prerequisite"}]
    conn, manager = connection([chunks, [{"id": 10}, {"id": 11}], relations])
    with patch.object(context_module, "get_ai_conn", return_value=manager):
        context = asyncio.run(build_learning_context(2, [AuthoringSource(content_id=9, title="Chapter PDF")]))
    assert context.sources[0]["text"].count("complete worked example") == 1
    assert "figure.png" in context.sources[0]["text"]
    assert context.sources[0]["chunk_ids"] == [20, 3]
    assert context.relations == relations
    sql = conn.fetch.await_args_list[0].args[0]
    assert "p.course_id=c.course_id" in sql and "p.content_id=c.content_id" in sql


def test_missing_one_selected_lesson_fails_instead_of_silently_omitting_it():
    _, manager = connection([[], []])
    with patch.object(context_module, "get_ai_conn", return_value=manager), pytest.raises(ValueError, match="Pending video"):
        asyncio.run(build_learning_context(2, [
            AuthoringSource(content_id=1, title="Ready text", type="TEXT", text="Ready material"),
            AuthoringSource(content_id=2, title="Pending video", type="VIDEO"),
        ]))


def sample_context():
    return LearningContext([
        {"content_id": 1, "title": "Definitions", "text": "Stacks use last-in-first-out ordering."},
        {"content_id": 2, "title": "Examples", "text": "Push A then B; pop returns B."},
    ], [10, 11, 12], [{"relation_type": "prerequisite"}])


def test_three_nodes_and_two_documents_can_form_one_complete_unit():
    prepared = SimpleNamespace(text="[SOURCE S1: Definitions]\nStacks use last-in-first-out ordering.\n\n[SOURCE S2: Examples]\nPush A then B; pop returns B.")
    raw = {"units": [{"title": "Trace a stack", "objective": "Predict the value popped after two pushes", "source_refs": ["S1", "S2"]}]}
    with patch.object(design_module, "prepare_authoring_context", new=AsyncMock(return_value=prepared)), patch.object(design_module, "chat_complete_json", new=AsyncMock(return_value=raw)):
        units = asyncio.run(plan_learning_units(sample_context(), kind="micro-lessons", language="en"))
    assert len(units) == 1
    assert units[0]["content_ids"] == [1, 2]
    assert "last-in-first-out" in units[0]["evidence"] and "pop returns B" in units[0]["evidence"]


@pytest.mark.parametrize("refs", [["S3"], ["S1"], []])
def test_plan_rejects_unknown_references_and_lost_lesson_coverage(refs):
    with patch.object(design_module, "prepare_authoring_context", new=AsyncMock(return_value=SimpleNamespace(text="Evidence"))), patch.object(design_module, "chat_complete_json", new=AsyncMock(return_value={"units": [{"title": "T", "objective": "O", "source_refs": refs}]})), pytest.raises(ValueError):
        asyncio.run(plan_learning_units(sample_context(), kind="quiz", language="en"))


@pytest.mark.parametrize("answers", [[False, False], [True, True], ["true", False]])
def test_bank_never_invents_or_repairs_a_correct_answer(answers):
    question = QuizGenerationService()._coerce_bank_question({
        "question_text": "What is removed from the stack?",
        "answer_options": [{"text": "A", "is_correct": answers[0]}, {"text": "B", "is_correct": answers[1]}],
    }, node_id=0, node_name="Stack", bloom_level="apply")
    assert question is None


def test_scoped_bank_question_uses_both_sources_and_preserves_provenance():
    from app.services import quiz_service as quiz_module
    units = [{"title": "Trace", "objective": "Predict pop", "source_refs": ["S1", "S2"], "content_ids": [1, 2],
              "sources": sample_context().sources,
              "evidence": "Stacks use last-in-first-out ordering. Push A then B; pop returns B."}]
    raw = {"question_text": "After pushing A then B, what is popped?", "answer_options": [
        {"text": "B", "is_correct": True}, {"text": "A", "is_correct": False}],
        "source_quote": "Push A then B; pop returns B.", "explanation": "Last in is first out."}
    with patch.object(context_module, "build_learning_context", new=AsyncMock(return_value=sample_context())), patch.object(design_module, "plan_learning_units", new=AsyncMock(return_value=units)), patch.object(quiz_module, "chat_complete_json", new=AsyncMock(return_value=raw)):
        questions, rejected = asyncio.run(QuizGenerationService().generate_for_bank(2, count=1, sources=[]))
    assert rejected == 0
    assert questions[0]["node_id"] is None
    assert questions[0]["settings"]["authoring_context"]["content_ids"] == [1, 2]
    assert questions[0]["settings"]["authoring_context"]["node_ids"] == [10, 11, 12]


def test_micro_quiz_count_is_independent_of_chunk_count():
    from app.services.micro_quiz_service import MicroQuizService, QuizQuestion
    service = MicroQuizService()
    unit = {"title": "Stacks", "objective": "Trace a stack", "evidence": "Definition + worked example + prerequisite evidence", "sources": sample_context().sources}
    answers = [QuizQuestion(q, [], "Explanation", "apply") for q in ["Define LIFO", "Trace push pop operations", "Compare queue ordering with stack behavior"]]
    with patch.object(service, "_generate_single_question", new=AsyncMock(side_effect=answers)) as generate:
        quiz = asyncio.run(service._generate_quiz_for_unit(unit, "en", 0))
    assert len(quiz.questions) == 3 and quiz.node_id is None
    assert all(call.kwargs["chunk_text"] == unit["evidence"] for call in generate.await_args_list)


def test_studio_curriculum_sources_replace_overlap_and_invalidate_old_plan():
    from app.services.studio.studio_service import StudioService
    service = StudioService()
    project = {"course_id": 2, "context_pack": [{"content_id": 1, "text": "old"}], "plan": {"title": "old plan"}}
    with patch.object(service, "get_project", new=AsyncMock(return_value=project)), patch.object(context_module, "lms_sources", new=AsyncMock(return_value=[])), patch.object(context_module, "build_learning_context", new=AsyncMock(return_value=sample_context())), patch.object(service, "_update", new=AsyncMock()) as update:
        result = asyncio.run(service.add_context_source("project", 7, {"type": "curriculum", "section_ids": [3]}))
    assert result["sources"] == 2
    saved = update.await_args.kwargs
    assert saved["plan"] is None and saved["artifacts"] == []
    assert [s["content_id"] for s in saved["context_pack"]] == [1, 2]
    assert "last-in-first-out" in saved["context_pack"][0]["text"]


def test_micro_lesson_failure_does_not_save_partial_coverage():
    from app.services.micro_lesson_service import MicroLessonService
    service = MicroLessonService()
    with patch.object(design_module, "plan_content_units", new=AsyncMock(return_value=[{"title": "First"}, {"title": "Second"}])), patch.object(service, "_generate_lesson_for_unit", new=AsyncMock(side_effect=[object(), None])), patch.object(service, "_post_lessons", new=AsyncMock()) as save, patch.object(service, "_post_status", new=AsyncMock()) as status:
        result = asyncio.run(service._generate_lessons(1, 2, 3, 4, 5, "en"))
    assert result.lessons == []
    save.assert_not_awaited()
    assert status.await_args.args[1] == "failed"
