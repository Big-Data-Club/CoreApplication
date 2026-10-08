#!/usr/bin/env python3
"""Emit a self-contained runner for the AI pod; no credentials leave that pod.

Usage: python3 scripts/apply-flashcard-migrations.py | kubectl exec -i POD -- python -
Existing manually applied V016/V017 are adopted only when all expected columns
exist. Each new migration and its ledger entry commit in one transaction.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {
    "V016": {"personal_flashcard_decks": ["id", "student_id", "name"], "personal_flashcards": ["id", "student_id", "deck_id", "revision", "legacy_id"], "personal_flashcard_reviews": ["id", "student_id", "card_id", "result"], "personal_flashcard_jobs": ["id", "student_id", "kind", "payload"]},
    "V017": {"personal_flashcard_decks": ["course_id"], "personal_flashcard_jobs": ["course_id"]},
    "V018": {"personal_flashcard_decks": ["source_content_id", "source_lesson_id"], "personal_flashcards": ["source_node_ids"]},
}


def emit():
    migrations = []
    for version, columns in VERSIONS.items():
        path, = (ROOT / "ai-service/migrations").glob(version + "__*.sql")
        migrations.append({"version": version, "columns": columns, "sql": path.read_text()})
    runner = Path(__file__).with_name("flashcard-migration-runner.py").read_text()
    print("MIGRATIONS = " + repr(migrations))
    print(runner)


if __name__ == "__main__":
    emit()
