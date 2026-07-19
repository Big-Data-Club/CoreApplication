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
        self.lock = threading.RLock()
        
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

            # 3. Notification tracking table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_notifications (
                    user_id BIGINT NOT NULL,
                    alert_type VARCHAR NOT NULL,
                    node_id BIGINT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sent_notifications_lookup 
                ON sent_notifications (user_id, alert_type, node_id)
            """)
            logger.info("DuckDB Tables initialized successfully")
            
            # Initialize Views
            self.refresh_views()

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
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=age_days)
        with self.lock:
            try:
                # Verify if there is data to archive
                res = self.conn.execute(
                    "SELECT COUNT(*) FROM bronze_interactions WHERE created_at < ?",
                    (cutoff_date,)
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
                        WHERE created_at < ?
                    ) TO '{temp_dir}' (
                        FORMAT 'PARQUET', 
                        PARTITION_BY (course_id, action_type),
                        OVERWRITE True
                    )
                """, (cutoff_date,))
                
                # Remove archived rows from active table
                self.conn.execute(
                    "DELETE FROM bronze_interactions WHERE created_at < ?",
                    (cutoff_date,)
                )
                logger.info(f"Archived {count} old interactions to Parquet under {temp_dir}")
                self.refresh_views()
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
                        COUNT(DISTINCT lesson_id) FILTER (WHERE action_type IN ('lesson_complete', 'lesson_completed')) as completed_lessons,
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

    def refresh_views(self):
        """Update or create Silver/Gold views dynamically based on Parquet file existence."""
        with self.lock:
            try:
                # Check if there are any parquet files in the bronze parquet directory
                has_parquet = False
                interactions_parquet_path = os.path.join(self.bronze_parquet_dir, "interactions")
                if os.path.exists(interactions_parquet_path):
                    # Check if there are actually files inside (recursively find .parquet)
                    for root, dirs, files in os.walk(interactions_parquet_path):
                        if any(f.endswith('.parquet') for f in files):
                            has_parquet = True
                            break
                
                if has_parquet:
                    parquet_pattern = os.path.join(interactions_parquet_path, "*", "*", "*.parquet").replace("\\", "/")
                    logger.info(f"Registering unified view with Parquet files at: {parquet_pattern}")
                    self.conn.execute(f"""
                        CREATE OR REPLACE VIEW unified_interactions AS
                        SELECT 
                            interaction_id, user_id, course_id, lesson_id, node_id, action_type, score, status, created_at
                        FROM bronze_interactions
                        UNION ALL
                        SELECT 
                            interaction_id, user_id, course_id, lesson_id, node_id, action_type, score, status, created_at
                        FROM read_parquet('{parquet_pattern}', union_by_name=True)
                    """)
                else:
                    logger.info("Registering unified view pointing only to bronze_interactions table")
                    self.conn.execute("""
                        CREATE OR REPLACE VIEW unified_interactions AS
                        SELECT 
                            interaction_id, user_id, course_id, lesson_id, node_id, action_type, score, status, created_at
                        FROM bronze_interactions
                    """)
                
                # Register Gold Views
                # A. Student course metrics
                self.conn.execute("""
                    CREATE OR REPLACE VIEW gold_student_course_metrics AS
                    WITH base_metrics AS (
                        SELECT 
                            user_id,
                            course_id,
                            COUNT(DISTINCT COALESCE(lesson_id, node_id)) FILTER (WHERE action_type IN ('lesson_complete', 'lesson_completed')) as completed_lessons_count,
                            COUNT(DISTINCT COALESCE(lesson_id, node_id)) FILTER (WHERE action_type IN ('lesson_view', 'lesson_viewed')) as viewed_lessons_count,
                            COUNT(*) FILTER (WHERE action_type = 'quick_check_correct') as correct_checks_count,
                            COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') as incorrect_checks_count,
                            COUNT(*) FILTER (WHERE action_type = 'ask_ai') as ask_ai_count,
                            COUNT(*) FILTER (WHERE action_type = 'flashcard_flip') as flashcard_flips_count,
                            COUNT(*) as total_interactions_count,
                            MAX(created_at) as last_active_at
                        FROM unified_interactions
                        GROUP BY user_id, course_id
                    )
                    SELECT 
                        *,
                        ROUND(
                            CASE 
                                WHEN (correct_checks_count + incorrect_checks_count) > 0 
                                THEN (correct_checks_count * 1.0 / (correct_checks_count + incorrect_checks_count))
                                ELSE 0.0 
                            END, 
                            2
                        ) as check_accuracy,
                        CASE 
                            WHEN flashcard_flips_count >= GREATEST(ask_ai_count, correct_checks_count + incorrect_checks_count, 1) THEN 'Chủ động (Flashcard)'
                            WHEN ask_ai_count >= GREATEST(flashcard_flips_count, correct_checks_count + incorrect_checks_count, 1) THEN 'Tương tác AI'
                            WHEN (correct_checks_count + incorrect_checks_count) >= GREATEST(flashcard_flips_count, ask_ai_count, 1) THEN 'Thực hành (Trắc nghiệm)'
                            ELSE 'Đọc hiểu & Lý thuyết'
                        END as learning_style,
                        CASE 
                            WHEN total_interactions_count >= 15 THEN 'Rất tích cực'
                            WHEN total_interactions_count >= 5 THEN 'Tích cực'
                            ELSE 'Cần cố gắng'
                        END as engagement_level,
                        CASE 
                            WHEN (correct_checks_count + incorrect_checks_count) = 0 THEN 'Nên làm thêm Quick Check để tự đánh giá.'
                            WHEN (correct_checks_count * 1.0 / (correct_checks_count + incorrect_checks_count)) < 0.6 THEN 'Độ chính xác thấp, nên xem kỹ lại lý thuyết và thảo luận với AI.'
                            WHEN flashcard_flips_count < 3 THEN 'Nên dùng Flashcards để ghi nhớ nhanh các khái niệm chính.'
                            WHEN ask_ai_count = 0 THEN 'Đừng ngần ngại sử dụng Hỏi AI khi gặp kiến thức khó.'
                            ELSE 'Đang học tập rất tốt! Hãy tiếp tục duy trì phong độ.'
                        END as study_recommendation
                    FROM base_metrics
                """)

                # B. Concept struggles
                self.conn.execute("""
                    CREATE OR REPLACE VIEW gold_concept_struggles AS
                    SELECT 
                        user_id,
                        course_id,
                        node_id,
                        COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') as incorrect_checks_count,
                        COUNT(*) FILTER (WHERE action_type = 'quick_check_correct') as correct_checks_count,
                        ROUND(
                            CASE 
                                WHEN (COUNT(*) FILTER (WHERE action_type = 'quick_check_correct') + COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect')) > 0 
                                THEN (COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') * 1.0 / (COUNT(*) FILTER (WHERE action_type = 'quick_check_correct') + COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect')))
                                ELSE 0.0 
                            END, 
                            2
                        ) as struggle_rate,
                        MAX(created_at) as last_attempt_at
                    FROM unified_interactions
                    WHERE node_id IS NOT NULL
                    GROUP BY user_id, course_id, node_id
                    HAVING COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') >= 1 
                       AND COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') > COUNT(*) FILTER (WHERE action_type = 'quick_check_correct')
                """)

                # C. User-Item Affinity Matrix (for DS ML Models)
                self.conn.execute("""
                    CREATE OR REPLACE VIEW gold_user_item_matrix AS
                    SELECT 
                        user_id,
                        course_id,
                        node_id,
                        COUNT(*) as total_interactions,
                        SUM(
                            CASE 
                                WHEN action_type IN ('lesson_view', 'lesson_viewed') THEN 1.0
                                WHEN action_type IN ('lesson_complete', 'lesson_completed') THEN 2.0
                                WHEN action_type = 'flashcard_flip' THEN 1.0
                                WHEN action_type = 'quick_check_correct' THEN 2.0
                                WHEN action_type = 'quick_check_incorrect' THEN 0.5
                                WHEN action_type = 'ask_ai' THEN 1.5
                                WHEN action_type = 'preference_elicited' THEN 3.0
                                ELSE 0.5
                            END
                        ) as implicit_affinity_score,
                        MAX(created_at) as last_interaction_at
                    FROM unified_interactions
                    WHERE node_id IS NOT NULL
                    GROUP BY user_id, course_id, node_id
                """)

                # D. Struggle Alerts
                self.conn.execute("""
                    CREATE OR REPLACE VIEW gold_struggle_alerts AS
                    -- 1. Concept Struggle
                    SELECT 
                        user_id,
                        course_id,
                        node_id,
                        'concept_struggle' as alert_type,
                        'Học viên đang gặp khó khăn ở khái niệm (Khái niệm ID: ' || CAST(node_id AS VARCHAR) || ') với tỷ lệ làm sai là ' || CAST(ROUND(struggle_rate * 100, 0) AS VARCHAR) || '%. Hãy ôn tập lại bài học!' as alert_message,
                        last_attempt_at as detected_at
                    FROM gold_concept_struggles
                    WHERE incorrect_checks_count >= 1
                    
                    UNION ALL
                    
                    -- 2. Low Performance Warning
                    SELECT 
                        user_id,
                        course_id,
                        NULL as node_id,
                        'low_performance' as alert_type,
                        'Cảnh báo: Bạn đang có độ chính xác Quick Check khá thấp (' || CAST(ROUND(check_accuracy * 100, 0) AS VARCHAR) || '%). Hãy dành thời gian xem kỹ lại lý thuyết.' as alert_message,
                        last_active_at as detected_at
                    FROM gold_student_course_metrics
                    WHERE (correct_checks_count + incorrect_checks_count) >= 3 AND check_accuracy < 0.60
                    
                    UNION ALL
                    
                    -- 3. Inactivity Warning
                    SELECT 
                        user_id,
                        course_id,
                        NULL as node_id,
                        'inactivity' as alert_type,
                        'Đã lâu bạn chưa tham gia học tập trong khóa học (Course ID: ' || CAST(course_id AS VARCHAR) || '). Hãy quay lại ôn luyện ngay nhé!' as alert_message,
                        last_active_at as detected_at
                    FROM gold_student_course_metrics
                    WHERE last_active_at < NOW() - INTERVAL 7 DAY
                    
                    UNION ALL
                    
                    -- 4. Positive Reinforcement
                    SELECT 
                        user_id,
                        course_id,
                        NULL as node_id,
                        'positive_reinforcement' as alert_type,
                        'Tuyệt vời! Bạn đang học tập rất tích cực với ' || CAST(completed_lessons_count AS VARCHAR) || ' bài học đã hoàn thành. Hãy tiếp tục phát huy nhé!' as alert_message,
                        last_active_at as detected_at
                    FROM gold_student_course_metrics
                    WHERE completed_lessons_count >= 3 AND engagement_level = 'Rất tích cực'
                    
                    UNION ALL
                    
                    -- 5. AI Helper Suggestion
                    SELECT 
                        user_id,
                        course_id,
                        NULL as node_id,
                        'ai_suggestion' as alert_type,
                        'Gợi ý: Bạn đang gặp một số câu hỏi khó ở chủ đề này. Hãy thử nhấn nút "Hỏi AI" ở góc phải để được giải thích chi tiết!' as alert_message,
                        last_active_at as detected_at
                    FROM gold_student_course_metrics
                    WHERE ask_ai_count = 0 AND (correct_checks_count + incorrect_checks_count) > 0 AND check_accuracy < 0.8
                    
                    UNION ALL
                    
                    -- 6. Flashcard Review Suggestion
                    SELECT 
                        user_id,
                        course_id,
                        NULL as node_id,
                        'flashcard_suggestion' as alert_type,
                        'Gợi ý: Bạn có thể sử dụng Thẻ ghi nhớ (Flashcards) để ôn tập nhanh các từ khóa quan trọng của bài học!' as alert_message,
                        last_active_at as detected_at
                    FROM gold_student_course_metrics
                    WHERE flashcard_flips_count = 0 AND viewed_lessons_count >= 2
                """)

                # E. Study Recommendations (Heuristics next best action)
                self.conn.execute("""
                    CREATE OR REPLACE VIEW gold_study_recommendations AS
                    WITH user_courses AS (
                        SELECT DISTINCT user_id, course_id FROM unified_interactions
                    ),
                    popular_concepts AS (
                        SELECT 
                            course_id,
                            node_id as popular_node_id,
                            COUNT(*) as interaction_count,
                            ROW_NUMBER() OVER (PARTITION BY course_id ORDER BY COUNT(*) DESC) as pop_rank
                        FROM unified_interactions
                        WHERE node_id IS NOT NULL AND action_type IN ('lesson_view', 'lesson_viewed', 'lesson_complete', 'lesson_completed')
                        GROUP BY course_id, node_id
                    ),
                    weakest_concepts AS (
                        SELECT 
                            user_id,
                            course_id,
                            node_id as weakest_node_id,
                            struggle_rate,
                            ROW_NUMBER() OVER (PARTITION BY user_id, course_id ORDER BY struggle_rate DESC) as rank
                        FROM gold_concept_struggles
                    ),
                    student_metrics AS (
                        SELECT 
                            user_id,
                            course_id,
                            check_accuracy,
                            viewed_lessons_count
                        FROM gold_student_course_metrics
                    )
                    SELECT 
                        uc.user_id,
                        uc.course_id,
                        CASE 
                            WHEN w.weakest_node_id IS NOT NULL THEN 'review_struggle_concept'
                            WHEN sm.check_accuracy < 0.60 AND sm.viewed_lessons_count > 0 THEN 'discuss_with_ai'
                            WHEN sm.viewed_lessons_count IS NULL OR sm.viewed_lessons_count = 0 THEN 'learn_popular_lesson'
                            ELSE 'learn_next_lesson'
                        END as recommended_action_type,
                        CASE 
                            WHEN w.weakest_node_id IS NOT NULL THEN w.weakest_node_id
                            WHEN sm.viewed_lessons_count IS NULL OR sm.viewed_lessons_count = 0 THEN pc.popular_node_id
                            ELSE NULL
                        END as recommended_node_id,
                        CASE 
                            WHEN w.weakest_node_id IS NOT NULL 
                                THEN 'Bạn đang gặp khó khăn ở khái niệm (ID: ' || CAST(w.weakest_node_id AS VARCHAR) || '). Hãy ôn tập lại lý thuyết bài học này!'
                            WHEN sm.check_accuracy < 0.60 AND sm.viewed_lessons_count > 0
                                THEN 'Cảnh báo: Độ chính xác Quick Check của bạn đang dưới 60%. Hãy thảo luận với AI Mentor để củng cố kiến thức.'
                            WHEN sm.viewed_lessons_count IS NULL OR sm.viewed_lessons_count = 0
                                THEN 'Khóa học mới! Hãy bắt đầu với chủ đề phổ biến nhất: (ID: ' || CAST(COALESCE(pc.popular_node_id, 0) AS VARCHAR) || ').'
                            ELSE 'Tiến độ học tập rất tốt! Hãy tiếp tục học bài học tiếp theo trong giáo trình.'
                        END as recommendation_message,
                        CURRENT_TIMESTAMP as generated_at
                    FROM user_courses uc
                    LEFT JOIN weakest_concepts w ON uc.user_id = w.user_id AND uc.course_id = w.course_id AND w.rank = 1
                    LEFT JOIN student_metrics sm ON uc.user_id = sm.user_id AND uc.course_id = sm.course_id
                    LEFT JOIN popular_concepts pc ON uc.course_id = pc.course_id AND pc.pop_rank = 1
                """)
                logger.info("DuckDB Silver and Gold Views refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh Lakehouse views: {str(e)}")

    def _query_to_dict_list(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                res = self.conn.execute(query, params).fetchall()
                cols = [desc[0] for desc in self.conn.description]
                return [dict(zip(cols, row)) for row in res]
            except Exception as e:
                logger.error(f"Failed to run query {query}: {str(e)}")
                return []

    def get_gold_student_metrics(self) -> List[Dict[str, Any]]:
        return self._query_to_dict_list("SELECT * FROM gold_student_course_metrics")

    def get_gold_concept_struggles(self) -> List[Dict[str, Any]]:
        return self._query_to_dict_list("SELECT * FROM gold_concept_struggles")

    def get_gold_user_item_matrix(self) -> List[Dict[str, Any]]:
        return self._query_to_dict_list("SELECT * FROM gold_user_item_matrix")

    def get_gold_struggle_alerts(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if user_id is not None:
            return self._query_to_dict_list("SELECT * FROM gold_struggle_alerts WHERE user_id = ?", (user_id,))
        return self._query_to_dict_list("SELECT * FROM gold_struggle_alerts")

    def get_gold_study_recommendations(self, user_id: Optional[int] = None, course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.lock:
            if user_id is not None and course_id is not None:
                return self._query_to_dict_list("SELECT * FROM gold_study_recommendations WHERE user_id = ? AND course_id = ?", (user_id, course_id))
            elif user_id is not None:
                return self._query_to_dict_list("SELECT * FROM gold_study_recommendations WHERE user_id = ?", (user_id,))
            return self._query_to_dict_list("SELECT * FROM gold_study_recommendations")

    def has_notification_been_sent_recently(self, user_id: int, alert_type: str, node_id: Optional[int], cooldown_hours: int = 24) -> bool:
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(hours=cooldown_hours)
        with self.lock:
            try:
                # Global per-user cooldown to prevent sending more than 1 email per day
                res = self.conn.execute("""
                    SELECT COUNT(*) FROM sent_notifications 
                    WHERE user_id = ? AND sent_at > ?
                """, (user_id, cutoff_time)).fetchone()
                return res[0] > 0 if res else False
            except Exception as e:
                logger.error(f"Error checking sent notifications: {e}")
                return False

    def record_sent_notification(self, user_id: int, alert_type: str, node_id: Optional[int]):
        with self.lock:
            try:
                self.conn.execute("""
                    INSERT INTO sent_notifications (user_id, alert_type, node_id, sent_at)
                    VALUES (?, ?, ?, ?)
                """, (user_id, alert_type, node_id, datetime.now()))
                logger.debug(f"Recorded notification sent to user={user_id}, type={alert_type}, node={node_id}")
            except Exception as e:
                logger.error(f"Error recording sent notification: {e}")

    def export_gold_tables(self) -> Dict[str, str]:
        """Export all Gold views to Parquet files in the gold lakehouse directory."""
        with self.lock:
            try:
                os.makedirs(self.gold_parquet_dir, exist_ok=True)
                tables = ["gold_student_course_metrics", "gold_concept_struggles", "gold_user_item_matrix", "gold_struggle_alerts", "gold_study_recommendations"]
                exports = {}
                for t in tables:
                    dest_file = os.path.join(self.gold_parquet_dir, f"{t}.parquet").replace("\\", "/")
                    self.conn.execute(f"COPY (SELECT * FROM {t}) TO '{dest_file}' (FORMAT 'PARQUET', OVERWRITE True)")
                    exports[t] = dest_file
                logger.info("Successfully exported Gold views to Parquet")
                return exports
            except Exception as e:
                logger.error(f"Failed to export Gold views: {e}")
                raise


# Singleton
lakehouse_service = LakehouseService()
