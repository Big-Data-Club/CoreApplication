package service

import (
	"context"
	"database/sql"
	"os"
	"testing"

	"example/hello/internal/repository"
	"example/hello/pkg/database"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
)

func TestFarmLearningAttemptAtomicAndIdempotent(t *testing.T) {
	url := os.Getenv("LMS_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set LMS_TEST_DATABASE_URL to a disposable PostgreSQL database")
	}
	ctx := context.Background()
	cfg, err := pgx.ParseConfig(url)
	if err != nil {
		t.Fatal(err)
	}
	admin := stdlib.OpenDB(*cfg)
	defer admin.Close()
	schema := "farm_lms_test_" + uuid.NewString()[:8]
	if _, err = admin.ExecContext(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	defer admin.ExecContext(ctx, "DROP SCHEMA "+schema+" CASCADE")
	cfg.RuntimeParams["search_path"] = schema
	db := stdlib.OpenDB(*cfg)
	defer db.Close()
	ddl := `CREATE TABLE users(id BIGINT PRIMARY KEY);
	CREATE TABLE courses(id BIGINT PRIMARY KEY,status TEXT NOT NULL);
	CREATE TABLE enrollments(student_id BIGINT,course_id BIGINT,status TEXT);
	CREATE TABLE question_bank_items(id BIGINT PRIMARY KEY,course_id BIGINT,node_id BIGINT,question_text TEXT,explanation TEXT,answer_options JSONB,status TEXT,question_type TEXT);
	CREATE TABLE micro_lesson_interactions(id BIGSERIAL PRIMARY KEY,user_id BIGINT,course_id BIGINT,node_id BIGINT,action_type TEXT,score DOUBLE PRECISION,status TEXT,payload JSONB,created_at TIMESTAMPTZ DEFAULT now());
	CREATE TABLE knowledge_node_mastery(user_id BIGINT,course_id BIGINT,node_id BIGINT,formal_quiz_score DOUBLE PRECISION DEFAULT 0,formal_quiz_count INT DEFAULT 0,mini_quiz_score DOUBLE PRECISION DEFAULT 0,mini_quiz_count INT DEFAULT 0,completion_score DOUBLE PRECISION DEFAULT 0,completion_count INT DEFAULT 0,engagement_score DOUBLE PRECISION DEFAULT 0,engagement_count INT DEFAULT 0,mastery_level DOUBLE PRECISION DEFAULT 0,last_interaction_at TIMESTAMPTZ,updated_at TIMESTAMPTZ,PRIMARY KEY(user_id,course_id,node_id));
	INSERT INTO users VALUES(41);INSERT INTO courses VALUES(9,'PUBLISHED');INSERT INTO enrollments VALUES(41,9,'ACCEPTED');
	INSERT INTO question_bank_items VALUES(7,9,55,'Lúa cho gì?','Lúa tạo ra thóc','[{"option_text":"Thóc","is_correct":true,"order_index":0},{"option_text":"Trứng","is_correct":false,"order_index":1}]','APPROVED','SINGLE_CHOICE');`
	if _, err = db.ExecContext(ctx, ddl); err != nil {
		t.Fatal(err)
	}
	if err = database.EnsureFarmLearningSchema(ctx, db); err != nil {
		t.Fatal(err)
	}
	if err = database.EnsureFarmLearningSchema(ctx, db); err != nil {
		t.Fatal("repeat migration", err)
	}
	svc := NewFarmLearningService(db, nil, repository.NewMicroInteractionRepository(db))
	q, err := svc.Question(ctx, 41, "quiz", "")
	if err != nil || q.Answer != "0" || q.CourseID != 9 {
		t.Fatalf("question: %+v %v", q, err)
	}
	if retry, e := svc.Question(ctx, 41, "quiz", q.ID); e != nil || retry.ID != q.ID {
		t.Fatalf("single question must remain retryable: %+v %v", retry, e)
	}
	if _, err = svc.Question(ctx, 42, "quiz", ""); err != sql.ErrNoRows {
		t.Fatalf("unenrolled learner got question: %v", err)
	}
	a := FarmAttempt{ChallengeID: uuid.NewString(), UserID: 41, CourseID: 9, NodeID: q.NodeID, SourceID: q.ID, Kind: "quiz", Correct: false}
	if err = svc.RecordAttempt(ctx, a); err != nil {
		t.Fatal(err)
	}
	if err = svc.RecordAttempt(ctx, a); err != nil {
		t.Fatal("retry", err)
	}
	var count int
	var mastery float64
	if err = db.QueryRowContext(ctx, `SELECT count(*) FROM micro_lesson_interactions`).Scan(&count); err != nil || count != 1 {
		t.Fatalf("interaction count %d %v", count, err)
	}
	if err = db.QueryRowContext(ctx, `SELECT mini_quiz_score FROM knowledge_node_mastery WHERE user_id=41 AND course_id=9 AND node_id=55`).Scan(&mastery); err != nil || mastery != 0 {
		t.Fatalf("mastery %f %v", mastery, err)
	}
	a.Correct = true
	if err = svc.RecordAttempt(ctx, a); err == nil {
		t.Fatal("conflicting retry accepted")
	}
}
