import os
import uuid
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
import duckdb

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LakehouseService:
    def __init__(self):
        self.db_dir = settings.data_dir
        os.makedirs(self.db_dir, exist_ok=True)
        
        # Bronze Parquet output directory
        self.bronze_parquet_dir = os.path.join(self.db_dir, "lakehouse", "bronze")
        os.makedirs(self.bronze_parquet_dir, exist_ok=True)
        
        # Gold Parquet output directory
        self.gold_parquet_dir = os.path.join(self.db_dir, "lakehouse", "gold")
        os.makedirs(self.gold_parquet_dir, exist_ok=True)

        self.db_path = os.path.join(self.db_dir, "student_analytics.duckdb")
        self.lock = threading.Lock()
        
        # Thread-safe persistent connection
        self.conn = duckdb.connect(self.db_path)
        self._init_tables()

    def _init_tables(self):
        with self.lock:
            # 1. Bronze: Raw Interactions
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS bronze_interactions (
                    interaction_id BIGINT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    course_id BIGINT NOT NULL,
                    lesson_id BIGINT,
                    node_id BIGINT,
                    action_type VARCHAR NOT NULL,
                    score DOUBLE,
                    status VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. Gold: Notebook entries
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS notebook_entries (
                    id VARCHAR PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    course_id BIGINT,
                    node_id BIGINT,
                    title VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("DuckDB Tables initialized successfully")

    # ── Ingestion ────────────────────────────────────────────────────────────

    def ingest_interaction(self, event: Dict[str, Any]):
        """Ingest raw micro-interaction into the Bronze table."""
        with self.lock:
            try:
                # Map payload fields
                interaction_id = event["interaction_id"]
                user_id = event["user_id"]
                course_id = event["course_id"]
                lesson_id = event.get("lesson_id")
                node_id = event.get("node_id")
                action_type = event["action_type"]
                score = event.get("score")
                status = event.get("status")
                
                created_at_str = event.get("created_at")
                if created_at_str:
                    # Parse standard ISO format (handling Z or offset)
                    try:
                        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    except ValueError:
                        created_at = datetime.now()
                else:
                    created_at = datetime.now()

                self.conn.execute("""
                    INSERT INTO bronze_interactions 
                    (interaction_id, user_id, course_id, lesson_id, node_id, action_type, score, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (interaction_id) DO NOTHING
                """, (interaction_id, user_id, course_id, lesson_id, node_id, action_type, score, status, created_at))
                logger.debug(f"Ingested micro-interaction: {interaction_id} for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to ingest interaction to DuckDB: {str(e)}")

    # ── Lakehouse Operations & Archival (Bronze -> Parquet) ──────────────────

    def archive_interactions_to_parquet(self, age_days: int = 7):
        """
        Lakehouse Pipeline: Move old Bronze raw logs into partitioned Parquet files.
        This keeps the active DuckDB database lightweight while preserving full logs.
        """
        with self.lock:
            try:
                # Verify if there is data to archive
                res = self.conn.execute(
                    "SELECT COUNT(*) FROM bronze_interactions WHERE created_at < NOW() - INTERVAL ? DAY",
                    (age_days,)
                ).fetchone()
                count = res[0] if res else 0
                
                if count == 0:
                    logger.debug("No old interactions to archive")
                    return
                
                temp_dir = os.path.join(self.bronze_parquet_dir, "interactions")
                os.makedirs(temp_dir, exist_ok=True)
                
                # Write partitioned parquet
                self.conn.execute(f"""
                    COPY (
                        SELECT * FROM bronze_interactions 
                        WHERE created_at < NOW() - INTERVAL ? DAY
                    ) TO '{temp_dir}' (
                        FORMAT 'PARQUET', 
                        PARTITION_BY (course_id, action_type),
                        OVERWRITE True
                    )
                """, (age_days,))
                
                # Remove archived rows from active table
                self.conn.execute(
                    "DELETE FROM bronze_interactions WHERE created_at < NOW() - INTERVAL ? DAY",
                    (age_days,)
                )
                logger.info(f"Archived {count} old interactions to Parquet under {temp_dir}")
            except Exception as e:
                logger.error(f"Failed to archive interactions to Parquet: {str(e)}")

    # ── Gold Queries: Personalization Profile ───────────────────────────────

    def get_student_profile(self, user_id: int, course_id: int) -> Dict[str, Any]:
        """
        Compute Gold student profile metrics using DuckDB.
        Aggregates clicks, quick checks, quiz successes, and weak spots.
        """
        with self.lock:
            try:
                # 1. Lesson completion metrics
                completion_res = self.conn.execute("""
                    SELECT 
                        COUNT(DISTINCT lesson_id) FILTER (WHERE action_type = 'lesson_completed') as completed_lessons,
                        COUNT(DISTINCT lesson_id) as attempted_lessons
                    FROM bronze_interactions
                    WHERE user_id = ? AND course_id = ?
                """, (user_id, course_id)).fetchone()
                
                completed_lessons = completion_res[0] if completion_res else 0
                attempted_lessons = completion_res[1] if completion_res else 0

                # 2. Quick check accuracies
                checks_res = self.conn.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE action_type = 'quick_check_correct') as correct_checks,
                        COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') as incorrect_checks
                    FROM bronze_interactions
                    WHERE user_id = ? AND course_id = ?
                """, (user_id, course_id)).fetchone()
                
                correct_checks = checks_res[0] if checks_res else 0
                incorrect_checks = checks_res[1] if checks_res else 0
                total_checks = correct_checks + incorrect_checks
                check_accuracy = (correct_checks / total_checks) if total_checks > 0 else 0.0

                # 3. Struggle concepts (nodes where incorrect checks > correct checks or count >= 2 incorrects)
                struggle_res = self.conn.execute("""
                    SELECT 
                        node_id,
                        COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') as incorrects,
                        COUNT(*) FILTER (WHERE action_type = 'quick_check_correct') as corrects
                    FROM bronze_interactions
                    WHERE user_id = ? AND course_id = ? AND node_id IS NOT NULL
                    GROUP BY node_id
                    HAVING incorrects > corrects OR incorrects >= 2
                    ORDER BY incorrects DESC
                    LIMIT 5
                """, (user_id, course_id)).fetchall()
                
                struggle_nodes = [r[0] for r in struggle_res]

                # 4. Recent activity timeline
                timeline_res = self.conn.execute("""
                    SELECT action_type, lesson_id, node_id, created_at
                    FROM bronze_interactions
                    WHERE user_id = ? AND course_id = ?
                    ORDER BY created_at DESC
                    LIMIT 3
                """, (user_id, course_id)).fetchall()
                
                recent_activities = []
                for r in timeline_res:
                    recent_activities.append({
                        "action_type": r[0],
                        "lesson_id": r[1],
                        "node_id": r[2],
                        "created_at": r[3].isoformat() if r[3] else None
                    })

                # Aggregate result
                profile = {
                    "user_id": user_id,
                    "course_id": course_id,
                    "completed_lessons": completed_lessons,
                    "attempted_lessons": attempted_lessons,
                    "correct_checks_count": correct_checks,
                    "incorrect_checks_count": incorrect_checks,
                    "check_accuracy": round(check_accuracy, 2),
                    "struggle_nodes": struggle_nodes,
                    "recent_activities": recent_activities,
                    "last_updated": datetime.now().isoformat()
                }
                
                # Write Gold Profile snapshot to gold parquet directory for future cold analysis
                self._save_gold_profile_parquet(profile)
                
                return profile
            except Exception as e:
                logger.error(f"Failed to query student personalization profile: {str(e)}")
                return {"user_id": user_id, "course_id": course_id, "error": str(e)}

    def _save_gold_profile_parquet(self, profile: Dict[str, Any]):
        """Save a quick snapshot to Parquet for analytical history of personalization changes."""
        try:
            # Flatten lists to prevent parquet structure limits
            flat = profile.copy()
            flat["struggle_nodes"] = ",".join(map(str, flat["struggle_nodes"]))
            flat["recent_activities"] = len(flat["recent_activities"]) # count only
            
            # Use temporary relation to write
            df = duckdb.df(flat)
            parquet_file = os.path.join(self.gold_parquet_dir, f"profile_{profile['user_id']}_{profile['course_id']}.parquet")
            duckdb.query("COPY df TO ? (FORMAT 'PARQUET')", (parquet_file,))
        except Exception as e:
            logger.debug(f"Failed to write Gold profile parquet: {str(e)}")

    # ── Notebook CRUD ────────────────────────────────────────────────────────

    def list_notebook_entries(self, user_id: int, course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                if course_id is not None:
                    res = self.conn.execute("""
                        SELECT id, user_id, course_id, node_id, title, content, created_at, updated_at
                        FROM notebook_entries
                        WHERE user_id = ? AND course_id = ?
                        ORDER BY updated_at DESC
                    """, (user_id, course_id)).fetchall()
                else:
                    res = self.conn.execute("""
                        SELECT id, user_id, course_id, node_id, title, content, created_at, updated_at
                        FROM notebook_entries
                        WHERE user_id = ?
                        ORDER BY updated_at DESC
                    """, (user_id,)).fetchall()
                
                entries = []
                for r in res:
                    entries.append({
                        "id": r[0],
                        "user_id": r[1],
                        "course_id": r[2],
                        "node_id": r[3],
                        "title": r[4],
                        "content": r[5],
                        "created_at": r[6].isoformat() if r[6] else None,
                        "updated_at": r[7].isoformat() if r[7] else None
                    })
                return entries
            except Exception as e:
                logger.error(f"Failed to list notebook entries: {str(e)}")
                return []

    def save_notebook_entry(self, user_id: int, title: str, content: str, course_id: Optional[int] = None, node_id: Optional[int] = None) -> Dict[str, Any]:
        with self.lock:
            try:
                entry_id = str(uuid.uuid4())
                now = datetime.now()
                self.conn.execute("""
                    INSERT INTO notebook_entries (id, user_id, course_id, node_id, title, content, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (entry_id, user_id, course_id, node_id, title, content, now, now))
                logger.info(f"Saved notebook entry {entry_id} for user {user_id}")
                return {
                    "id": entry_id,
                    "user_id": user_id,
                    "course_id": course_id,
                    "node_id": node_id,
                    "title": title,
                    "content": content,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat()
                }
            except Exception as e:
                logger.error(f"Failed to save notebook entry: {str(e)}")
                raise

    def delete_notebook_entry(self, entry_id: str, user_id: int):
        with self.lock:
            try:
                self.conn.execute("""
                    DELETE FROM notebook_entries
                    WHERE id = ? AND user_id = ?
                """, (entry_id, user_id))
                logger.info(f"Deleted notebook entry {entry_id} for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to delete notebook: {str(e)}")
                raise


# Singleton
lakehouse_service = LakehouseService()
