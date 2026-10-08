import asyncio
import importlib.util
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from pydantic import ValidationError
from app.services.content_study_service import ContentGeneration, Question


def test_rejects_ambiguous_source_and_invalid_quiz():
    for source in ({"title": "T"}, {"title": "T", "content_id": 1, "lesson_id": 2}):
        with pytest.raises(ValidationError):
            ContentGeneration(source=source, request_id=uuid4())
    for flags in ([True, True], [False, False], ["true", False]):
        with pytest.raises(ValidationError):
            Question(question_text="Q", answer_options=[{"text": str(i), "is_correct": flag} for i, flag in enumerate(flags)])


@pytest.mark.skipif(not os.environ.get("FLASHCARD_TEST_DSN"), reason="isolated PostgreSQL DSN required")
def test_content_jobs_grounding_atomic_save_and_migration_adoption(monkeypatch):
    import asyncpg
    import app.services.personal_flashcard_service as service
    root = Path(__file__).parents[2]

    async def scenario():
        conn = await asyncpg.connect(os.environ["FLASHCARD_TEST_DSN"])
        schema = "content_study_test_" + uuid4().hex
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')
        @asynccontextmanager
        async def connection():
            yield conn
        monkeypatch.setattr(service, "get_ai_conn", connection)
        try:
            await conn.execute("""CREATE TABLE flashcards(id BIGINT, student_id BIGINT, course_id BIGINT, front_text TEXT, back_text TEXT, status TEXT);
                CREATE TABLE flashcard_repetitions(flashcard_id BIGINT, student_id BIGINT, repetitions INT, interval_days INT, easiness_factor FLOAT, next_review_date DATE);
                CREATE TABLE knowledge_nodes(id BIGINT,course_id BIGINT,source_content_id BIGINT,name TEXT,description TEXT);
                CREATE TABLE document_chunks(id BIGINT,course_id BIGINT,content_id BIGINT,node_id BIGINT,status TEXT,chunk_level TEXT,chunk_index INT,chunk_text TEXT);
                INSERT INTO knowledge_nodes VALUES(1,7,9,'Stack','LIFO'),(2,8,9,'Private other course','SECRET'),(3,7,99,'Unrelated','OTHER'),(4,7,50,'Indexed node','FIFO');
                INSERT INTO document_chunks VALUES(1,7,9,4,'ready','child',0,'Queues are FIFO'),(2,8,9,2,'ready','child',0,'SECRET'),(3,7,99,3,'ready','child',0,'OTHER');
            """)
            migrations = []
            spec = importlib.util.spec_from_file_location("flashcard_emit", root / "scripts/apply-flashcard-migrations.py")
            emit = importlib.util.module_from_spec(spec); spec.loader.exec_module(emit)
            for version, columns in emit.VERSIONS.items():
                path, = (root / "ai-service/migrations").glob(version + "__*.sql")
                migrations.append({"version": version, "columns": columns, "sql": path.read_text()})
            # Simulate user's manually applied V016/V017, then upgrade twice.
            await conn.execute(migrations[0]["sql"])
            await conn.execute(migrations[1]["sql"])
            spec = importlib.util.spec_from_file_location("flashcard_runner", root / "scripts/flashcard-migration-runner.py")
            runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
            await runner.apply(conn, migrations)
            await runner.apply(conn, migrations)
            assert await conn.fetchval("SELECT count(*) FROM flashcard_schema_migrations") == 3
            llm = ModuleType("app.core.llm")
            gateway = ModuleType("app.core.llm_gateway")
            gateway.TASK_FLASHCARD_GEN = "flashcard_gen"; gateway.TASK_QUIZ_GEN = "quiz_gen"
            prompts = []
            async def complete(messages, **kwargs):
                prompts.append(json.loads(messages[1]["content"]))
                if kwargs["task"] == "quiz_gen":
                    return {"questions": [{"question_text": "Which order?", "answer_options": [{"text": "LIFO", "is_correct": True}, {"text": "FIFO", "is_correct": False}]}]}
                return {"cards": [{"front_text": "Stack order?", "back_text": "LIFO"}]}
            llm.chat_complete_json = complete
            monkeypatch.setitem(sys.modules, "app.core.llm", llm)
            monkeypatch.setitem(sys.modules, "app.core.llm_gateway", gateway)
            data = {"source": {"content_id": 9, "title": "Data structures", "text": "Stacks are LIFO"}, "request_id": str(uuid4()), "count": 5}
            job = await service.library_action(42,7,"generate_content",data)
            with pytest.raises(ValueError):
                await service.library_action(43,7,"generate_content",data)
            with pytest.raises(LookupError):
                await service.library_action(42,8,"job",job)
            await service.process_personal_flashcard_job(job["job_id"])
            await service.process_personal_flashcard_job(job["job_id"])
            status = await service.library_action(42,7,"job",job)
            assert status["status"] == "completed", status
            assert status["result"]["saved_count"] == 1
            assert status["result"]["node_ids"] == [1,4]
            assert len(prompts) == 1 and prompts[0]["material"] == "Stacks are LIFO"
            assert "SECRET" not in json.dumps(prompts) and "OTHER" not in json.dumps(prompts)
            library = await service.library_action(42,7,"list",{})
            assert len(library["decks"]) == 1 and len(library["cards"]) == 1
            assert library["cards"][0]["source_node_ids"] == [1,4]
            assert (await service.library_action(43,7,"list",{}))["cards"] == []
            assert (await service.library_action(42,8,"list",{}))["cards"] == []
            # Retry returns original completed job, without creating another card.
            retry = await service.library_action(42,7,"generate_content",data)
            await service.process_personal_flashcard_job(retry["job_id"])
            assert len(prompts) == 1
            # A second explicit generation appends to the same source deck.
            data["request_id"] = str(uuid4())
            data["source"]["text"] = ""
            job2 = await service.library_action(42,7,"generate_content",data)
            await service.process_personal_flashcard_job(job2["job_id"])
            assert prompts[-1]["material"] == "Queues are FIFO"
            assert await conn.fetchval("SELECT count(*) FROM personal_flashcard_decks") == 1
            assert await conn.fetchval("SELECT count(*) FROM personal_flashcards") == 2
            # Quiz returns questions, does not create cards or decks.
            data["request_id"] = str(uuid4())
            quiz = await service.library_action(42,7,"quiz_content",data)
            await service.process_personal_flashcard_job(quiz["job_id"])
            quiz_status = await service.library_action(42,7,"job",quiz)
            assert len(quiz_status["result"]["questions"]) == 1
            assert await conn.fetchval("SELECT count(*) FROM personal_flashcards") == 2
            # Empty source fails without calling a model or saving a deck.
            data["request_id"] = str(uuid4()); data["source"]["content_id"] = 100
            missing = await service.library_action(42,7,"generate_content",data)
            calls = len(prompts)
            await service.process_personal_flashcard_job(missing["job_id"])
            status = await service.library_action(42,7,"job",missing)
            assert status["status"] == "failed" and "chưa có nội dung" in status["error"]
            assert len(prompts) == calls
            # Invalid AI output rolls back all writes; failed retry can recover.
            async def invalid(*args, **kwargs):
                return {"cards": [{"front_text": "Q", "back_text": "A"}, {"front_text": "", "back_text": "Invalid"}]}
            llm.chat_complete_json = invalid
            data["request_id"] = str(uuid4()); data["source"]["content_id"] = 9
            invalid_job = await service.library_action(42,7,"generate_content",data)
            await service.process_personal_flashcard_job(invalid_job["job_id"])
            assert (await service.library_action(42,7,"job",invalid_job))["status"] == "failed"
            assert await conn.fetchval("SELECT count(*) FROM personal_flashcards") == 2
            llm.chat_complete_json = complete
            await service.library_action(42,7,"generate_content",data)
            await service.process_personal_flashcard_job(invalid_job["job_id"])
            assert (await service.library_action(42,7,"job",invalid_job))["status"] == "completed"
        finally:
            await conn.execute('SET search_path TO public')
            await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await conn.close()
    asyncio.run(scenario())
