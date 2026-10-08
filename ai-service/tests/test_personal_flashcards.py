import json
from datetime import timedelta

import pytest
from pydantic import ValidationError
from app.services.personal_flashcard_service import CardDraft, Verdict, exact_match, normalize_answer, schedule


@pytest.mark.parametrize("reference,answer,expected", [
    ("Hello world", "  HELLO\nworld ", True),
    ("café", "cafe\u0301", True),
    ("café", "cafe", False),
    ("C++", "C", False),
    ("-1", "1", False),
    ("a != b", "a = b", False),
    ("O(n)", "O(n²)", False),
    ("a b", "ab", False),
    ("yes", "", False),
])
def test_exact_matching_preserves_meaning(reference, answer, expected):
    assert exact_match({"back_text": reference}, answer) is expected


def test_alternatives_and_case_sensitive_cards():
    card = {"back_text": "CPU", "accepted_answers": json.dumps(["central processing unit"]), "case_sensitive": True}
    assert exact_match(card, "central processing unit")
    assert not exact_match(card, "cpu")
    assert normalize_answer("x  +  y", True) == "x + y"


def test_schedule_relearns_misses_and_spaces_correct_answers():
    rep, interval, ease, delay = schedule(False, 8, 90, 2.5)
    assert (rep, interval, delay) == (0, 0, timedelta(minutes=10))
    assert ease >= 1.3
    assert schedule(True, 0, 0, 2.5)[1] == 1
    assert schedule(True, 1, 1, 2.5)[1] == 6
    assert schedule(True, 2, 6, 2.5)[1] > 6


def test_drafts_and_ai_verdicts_are_validated():
    with pytest.raises(ValidationError):
        CardDraft(front_text=" ", back_text="answer")
    with pytest.raises(ValidationError):
        CardDraft(front_text="question", back_text="answer", accepted_answers=[""])
    with pytest.raises(ValidationError):
        Verdict(correct="false", feedback="No")
    with pytest.raises(ValidationError):
        CardDraft(front_text="question", back_text="answer", language="<script>")


@pytest.mark.skipif(not __import__("os").environ.get("FLASHCARD_TEST_DSN"), reason="isolated PostgreSQL DSN required")
def test_library_database_ownership_migration_and_review_idempotency(monkeypatch):
    import asyncio
    import os
    from contextlib import asynccontextmanager
    from pathlib import Path
    from uuid import uuid4
    import asyncpg
    import app.services.personal_flashcard_service as service

    async def scenario():
        conn = await asyncpg.connect(os.environ["FLASHCARD_TEST_DSN"])
        schema = "flashcards_test_" + uuid4().hex
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')

        @asynccontextmanager
        async def connection():
            yield conn
        monkeypatch.setattr(service, "get_ai_conn", connection)
        try:
            await conn.execute("""CREATE TABLE flashcards(id BIGINT, student_id BIGINT, course_id BIGINT, front_text TEXT, back_text TEXT, status TEXT);
                CREATE TABLE flashcard_repetitions(flashcard_id BIGINT, student_id BIGINT, repetitions INT, interval_days INT, easiness_factor FLOAT, next_review_date DATE);
                INSERT INTO flashcards VALUES(9,1,7,'CPU','Central processing unit','ACTIVE'),(10,1,8,'Hello','Xin chào','ACTIVE');
                INSERT INTO flashcard_repetitions VALUES(9,1,2,6,2.5,CURRENT_DATE+6);""")
            await conn.execute((Path(__file__).parents[1] / "migrations/V016__personal_flashcard_library.sql").read_text())
            # Simulate V016 already applied, including a newly created unscoped card.
            orphan = await conn.fetchval("INSERT INTO personal_flashcard_decks(student_id,name) VALUES(1,'New cards') RETURNING id")
            await conn.execute("INSERT INTO personal_flashcards(student_id,deck_id,front_text,back_text) VALUES(1,$1,'Q','A')", orphan)
            await conn.execute((Path(__file__).parents[1] / "migrations/V017__flashcard_library_course_scope.sql").read_text())
            library = await service.library_action(1, 7, "list", {})
            assert library["cards"][0]["repetitions"] == 2
            assert library["cards"][0]["legacy_id"] == 9
            assert (await service.library_action(2, 7, "list", {}))["cards"] == []
            assert (await service.library_action(1, 8, "list", {}))["cards"][0]["legacy_id"] == 10
            assert library["unassigned_decks"][0]["id"] == orphan
            await service.library_action(1, 8, "assign_deck", {"deck_id": orphan})
            assert len((await service.library_action(1, 8, "list", {}))["cards"]) == 2

            deck = await service.library_action(1, 7, "create_deck", {"name": "Computer science"})
            draft = {"front_text": "Language", "back_text": "C++"}
            saved = await service.library_action(1, 7, "save_cards", {"deck_id": deck["id"], "cards": [draft]})
            card = saved["cards"][0]
            for action, data in [
                ("save_cards", {"deck_id": deck["id"], "cards": [draft]}),
                ("delete_card", {"card_id": card["id"]}),
                ("delete_deck", {"deck_id": deck["id"]}),
                ("rename_deck", {"deck_id": deck["id"], "name": "Stolen"}),
                ("check", {"card_id": card["id"], "answer": "C++", "review_id": str(uuid4()), "revision": 1}),
            ]:
                with pytest.raises(LookupError):
                    await service.library_action(2, 7, action, data)
            for action, data in [
                ("delete_card", {"card_id": card["id"]}),
                ("save_cards", {"deck_id": deck["id"], "cards": [draft]}),
                ("delete_deck", {"deck_id": deck["id"]}),
                ("check", {"card_id": card["id"], "answer": "C++", "review_id": str(uuid4()), "revision": 1}),
            ]:
                with pytest.raises(LookupError):
                    await service.library_action(1, 8, action, data)
            request = {"card_id": card["id"], "answer": "C++", "review_id": str(uuid4()), "revision": 1}
            first = await service.library_action(1, 7, "check", request)
            again = await service.library_action(1, 7, "check", request)
            assert first == again and first["correct"]
            assert await conn.fetchval("SELECT repetitions FROM personal_flashcards WHERE id=$1", card["id"]) == 1
            await service.library_action(1, 7, "save_cards", {"deck_id": deck["id"], "cards": [{**draft, "id": card["id"], "back_text": "Python"}]})
            with pytest.raises(ValueError, match="thay đổi"):
                await service.library_action(1, 7, "check", {**request, "review_id": str(uuid4())})
            job = await service.library_action(1, 7, "generate", {"topic": "Binary search"})
            with pytest.raises(LookupError):
                await service.library_action(2, 7, "job", {"job_id": job["job_id"]})
            # Model output is a draft; duplicate deliveries never save cards or
            # apply a second review, and malformed verdicts leave progress alone.
            import sys
            from types import ModuleType
            llm = ModuleType("app.core.llm")
            gateway = ModuleType("app.core.llm_gateway")
            gateway.TASK_FLASHCARD_GEN = "flashcard_gen"
            calls = []
            async def generate(*args, **kwargs):
                calls.append(1)
                return {"cards": [{"front_text": "Stack order?", "back_text": "LIFO"}]}
            llm.chat_complete_json = generate
            monkeypatch.setitem(sys.modules, "app.core.llm", llm)
            monkeypatch.setitem(sys.modules, "app.core.llm_gateway", gateway)
            await service.process_personal_flashcard_job(job["job_id"])
            await service.process_personal_flashcard_job(job["job_id"])
            assert len(calls) == 1
            result = await service.library_action(1, 7, "job", {"job_id": job["job_id"]})
            assert result["result"]["cards"][0]["back_text"] == "LIFO"
            assert await conn.fetchval("SELECT count(*) FROM personal_flashcards WHERE front_text='Stack order?'") == 0
            ai_card = (await service.library_action(1, 7, "save_cards", {"deck_id": deck["id"], "cards": [{"front_text": "Stack order?", "back_text": "LIFO", "match_mode": "ai"}]}))["cards"][0]
            ai_answer = {"card_id": ai_card["id"], "answer": "Last in, first out", "review_id": str(uuid4()), "revision": 1}
            check_job = await service.library_action(1, 7, "check", ai_answer)
            async def malformed(*args, **kwargs):
                return {"correct": "true", "feedback": "Invalid string verdict"}
            llm.chat_complete_json = malformed
            await service.process_personal_flashcard_job(check_job["job_id"])
            assert (await service.library_action(1, 7, "job", {"job_id": check_job["job_id"]}))["status"] == "failed"
            assert await conn.fetchval("SELECT repetitions FROM personal_flashcards WHERE id=$1", ai_card["id"]) == 0
            async def valid(*args, **kwargs):
                return {"correct": True, "feedback": "Chính xác!"}
            llm.chat_complete_json = valid
            await service.library_action(1, 7, "check", ai_answer)
            await service.process_personal_flashcard_job(check_job["job_id"])
            await service.process_personal_flashcard_job(check_job["job_id"])
            assert await conn.fetchval("SELECT repetitions FROM personal_flashcards WHERE id=$1", ai_card["id"]) == 1
            reveal = await service.library_action(1, 7, "check", {"card_id": ai_card["id"], "reveal": True, "review_id": str(uuid4()), "revision": 1})
            assert reveal["correct"] is False
            assert reveal["back_text"] == "LIFO"
            assert await conn.fetchval("SELECT repetitions FROM personal_flashcards WHERE id=$1", ai_card["id"]) == 0
            await service.library_action(1, 7, "delete_deck", {"deck_id": deck["id"]})
            assert not await conn.fetchval("SELECT id FROM personal_flashcards WHERE id=$1", card["id"])
        finally:
            await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await conn.close()
    asyncio.run(scenario())
