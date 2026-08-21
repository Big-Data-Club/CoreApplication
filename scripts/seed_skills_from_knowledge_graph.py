#!/usr/bin/env python3
"""
Seed the personalized-learning skill taxonomy from the AI knowledge graph.

Sources (real data, read from the databases configured in .env):
  • ai.knowledge_nodes            -> skills        (one skill per knowledge node)
  • lms.quiz_questions.node_id    -> question_skills (bloom-level based difficulty)
  • ai.knowledge_nodes.source_content_id -> content_skills

Idempotent: re-running updates nothing it has already seeded. Skills are
matched to knowledge nodes via skills.metadata->>'knowledge_node_id'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

REPO_ROOT = Path(__file__).resolve().parent.parent

BLOOM_DIFFICULTY = {
    "remember": 0.20,
    "understand": 0.35,
    "apply": 0.50,
    "analyze": 0.65,
    "evaluate": 0.80,
    "create": 0.90,
}
DEFAULT_DIFFICULTY = 0.50


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = REPO_ROOT / ".env"
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def connect(env: dict[str, str], prefix: str):
    return psycopg2.connect(
        host=env[f"{prefix}_POSTGRES_HOST"],
        dbname=env[f"{prefix}_POSTGRES_DB"],
        user=env[f"{prefix}_POSTGRES_USER"],
        password=env[f"{prefix}_POSTGRES_PASSWORD"],
        sslmode="require",
    )


def seed() -> None:
    env = load_env()
    ai = connect(env, "AI")
    lms = connect(env, "LMS")
    ai_cur = ai.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    lms_cur = lms.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── 1. Pull the knowledge graph ────────────────────────────────────────
    ai_cur.execute(
        """
        SELECT kn.id, kn.course_id, kn.name, COALESCE(kn.name_vi, kn.name) AS name_vi,
               kn.description, kn.source_content_id
        FROM knowledge_nodes kn
        ORDER BY kn.course_id, kn.id
        """
    )
    nodes = ai_cur.fetchall()
    print(f"knowledge_nodes fetched: {len(nodes)}")

    lms_cur.execute("SELECT id, title FROM courses")
    course_titles = {row["id"]: row["title"] for row in lms_cur.fetchall()}

    # ── 2. Existing skill state (for idempotency) ──────────────────────────
    lms_cur.execute(
        """
        SELECT id,
               metadata->>'knowledge_node_id' AS node_id,
               name
        FROM skills
        """
    )
    skill_by_node: dict[str, int] = {}
    taken_names: set[str] = set()
    for row in lms_cur.fetchall():
        if row["node_id"]:
            skill_by_node[str(row["node_id"])] = row["id"]
        taken_names.add(row["name"].casefold())

    # ── 3. Insert missing skills ───────────────────────────────────────────
    inserted_skills = 0
    for node in nodes:
        node_key = str(node["id"])
        if node_key in skill_by_node:
            continue

        base_name = (node["name_vi"] or node["name"]).strip()
        name = base_name
        suffix = 2
        # Names are shared across courses; disambiguate with the course title.
        while name.casefold() in taken_names:
            course_title = course_titles.get(node["course_id"], f"course {node['course_id']}")
            name = f"{base_name} — {course_title}"
            if name.casefold() in taken_names:
                name = f"{base_name} — {course_title} ({suffix})"
                suffix += 1
        taken_names.add(name.casefold())

        metadata = json.dumps(
            {
                "knowledge_node_id": node["id"],
                "course_id": node["course_id"],
                "source_content_id": node["source_content_id"],
                "seeded_by": "seed_skills_from_knowledge_graph.py",
            }
        )
        lms_cur.execute(
            """
            INSERT INTO skills (name, description, difficulty, metadata)
            VALUES (%s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (name, node["description"], None, metadata),
        )
        skill_by_node[node_key] = lms_cur.fetchone()["id"]
        inserted_skills += 1
    print(f"skills inserted: {inserted_skills} (total known: {len(skill_by_node)})")

    # ── 4. question_skills from quiz_questions.node_id ─────────────────────
    lms_cur.execute(
        """
        SELECT qq.id, qq.node_id, COALESCE(qq.bloom_level, '') AS bloom_level
        FROM quiz_questions qq
        WHERE qq.node_id IS NOT NULL
        """
    )
    questions = lms_cur.fetchall()
    question_rows = []
    skipped_no_skill = 0
    for q in questions:
        skill_id = skill_by_node.get(str(q["node_id"]))
        if not skill_id:
            skipped_no_skill += 1
            continue
        difficulty = BLOOM_DIFFICULTY.get(q["bloom_level"], DEFAULT_DIFFICULTY)
        question_rows.append((q["id"], skill_id, difficulty, 1.0))
    psycopg2.extras.execute_values(
        lms_cur,
        """
        INSERT INTO question_skills (question_id, skill_id, difficulty, weight)
        VALUES %s
        ON CONFLICT (question_id, skill_id) DO NOTHING
        """,
        question_rows,
    )
    print(f"question_skills mapped: {len(question_rows)} (skipped {skipped_no_skill}: unknown node)")

    # ── 5. content_skills from knowledge_nodes.source_content_id ───────────
    # Only map content that still exists in the LMS catalogue: knowledge
    # nodes may reference content deleted or lost across migrations.
    lms_cur.execute("SELECT id FROM section_content")
    existing_content = {row["id"] for row in lms_cur.fetchall()}
    content_rows = []
    skipped_stale_content = 0
    for node in nodes:
        if not node["source_content_id"]:
            continue
        if node["source_content_id"] not in existing_content:
            skipped_stale_content += 1
            continue
        skill_id = skill_by_node.get(str(node["id"]))
        if not skill_id:
            continue
        content_rows.append((node["source_content_id"], skill_id, DEFAULT_DIFFICULTY, 1.0))
    psycopg2.extras.execute_values(
        lms_cur,
        """
        INSERT INTO content_skills (content_id, skill_id, difficulty, weight)
        VALUES %s
        ON CONFLICT (content_id, skill_id) DO NOTHING
        """,
        content_rows,
    )
    print(f"content_skills mapped: {len(content_rows)} (skipped {skipped_stale_content}: stale content refs)")

    lms.commit()

    # ── 6. Summary ─────────────────────────────────────────────────────────
    for table in ("skills", "question_skills", "content_skills"):
        lms_cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
        print(f"{table}: {lms_cur.fetchone()['n']} rows total")

    lms_cur.execute(
        """
        SELECT c.title, COUNT(DISTINCT cs.skill_id) AS skills
        FROM content_skills cs
        JOIN section_content sc ON sc.id = cs.content_id
        JOIN course_sections sec ON sec.id = sc.section_id
        JOIN courses c ON c.id = sec.course_id
        GROUP BY c.title
        ORDER BY skills DESC
        LIMIT 10
        """
    )
    print("\nTop courses by mappable content:")
    for row in lms_cur.fetchall():
        print(f"  {row['skills']:4d} skills | {row['title']}")

    ai_cur.close()
    lms_cur.close()
    ai.close()
    lms.close()


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:  # noqa: BLE001
        print(f"SEED FAILED: {exc}", file=sys.stderr)
        raise
