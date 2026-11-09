import threading
from unittest.mock import patch

import duckdb
import pytest
from app.services.lakehouse import LakehouseService


@pytest.fixture
def lake(tmp_path):
    service = LakehouseService.__new__(LakehouseService)
    service.conn = duckdb.connect(":memory:")
    service.lock = threading.RLock()
    service.bronze_parquet_dir = str(tmp_path / "bronze")
    service.gold_parquet_dir = str(tmp_path)
    service._init_tables()
    yield service
    service.conn.close()


def test_http_profile_reads_only_snapshot_and_does_not_export(lake):
    assert lake.get_student_profile(7, 10)["profile_available"] is False
    lake.ingest_interaction({"interaction_id": 1, "user_id": 7, "course_id": 10, "lesson_id": 4, "action_type": "lesson_complete"})
    # Ingest does not turn an HTTP read into a heavy computation.
    assert lake.get_student_profile(7, 10)["profile_available"] is False
    profile = lake.refresh_student_profile(7, 10)
    assert profile["completed_lessons"] == 1
    assert profile["check_accuracy"] is None
    with patch.object(lake, "refresh_student_profile", side_effect=AssertionError("HTTP aggregation")), patch.object(lake, "_save_gold_profile_parquet", side_effect=AssertionError("HTTP export")):
        assert lake.get_student_profile(7, 10)["completed_lessons"] == 1
    assert lake.get_student_profile(8, 10)["profile_available"] is False


def test_feedback_replay_late_events_and_user_isolation(lake):
    event = {"event_id": "e1", "user_id": 7, "course_id": 10, "event_type": "not_interested", "recommendation_id": "rec1", "event_time": "2099-01-01T00:00:00Z"}
    lake.ingest_recommendation_event(event)
    lake.ingest_recommendation_event(event)
    lake.ingest_recommendation_event({**event, "event_id": "e0", "event_time": "2098-12-31T00:00:00Z"})
    profile = lake.refresh_recommendation_profile(7)
    assert profile["courses"]["10"]["not_interested"]["count"] == 2
    assert profile["courses"]["10"]["not_interested"]["at"].startswith("2099-01-01")
    assert lake.get_student_profile(8, 0)["profile_available"] is False


def test_backfill_existing_history_and_repeated_initialization(lake):
    lake.ingest_interaction({"interaction_id": 2, "user_id": 7, "course_id": 10, "action_type": "quick_check_correct"})
    lake.backfill_profile_snapshots()
    assert lake.get_student_profile(7, 10)["check_accuracy"] == 1
    assert "10" in lake.get_student_profile(7, 0)["courses"]
    lake._init_tables()
    assert lake.get_student_profile(7, 10)["check_accuracy"] == 1


def test_archived_history_is_preserved_in_profiles(lake):
    lake.ingest_interaction({"interaction_id": 3, "user_id": 7, "course_id": 10, "lesson_id": 4, "action_type": "lesson_complete", "created_at": "2000-01-01T00:00:00Z"})
    lake.archive_interactions_to_parquet(age_days=7)
    assert lake.conn.execute("SELECT COUNT(*) FROM bronze_interactions").fetchone()[0] == 0
    assert lake.refresh_student_profile(7, 10)["completed_lessons"] == 1
