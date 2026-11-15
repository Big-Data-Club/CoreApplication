package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sync"
	"testing"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/testutil"
)

func TestCreateQuestionRollsBackAllWrites(t *testing.T) {
	db := testutil.Database(t)
	testutil.SeedQuiz(t, db)
	if _, err := db.Exec(`CREATE FUNCTION reject_option() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture insert failure'; END $$;
 CREATE TRIGGER fixture_reject BEFORE INSERT ON quiz_answer_options FOR EACH ROW EXECUTE FUNCTION reject_option()`); err != nil {
		t.Fatal(err)
	}
	q := &models.QuizQuestion{QuizID: 1, QuestionType: models.QuestionTypeSingleChoice, QuestionText: "Rollback", Points: 1, OrderIndex: 1, Settings: []byte(`{}`)}
	err := NewQuizRepository(db).CreateQuestionWithAnswers(context.Background(), q, []models.QuizAnswerOption{{OptionText: "failure", OrderIndex: 1}}, nil)
	if err == nil {
		t.Fatal("injected failure was ignored")
	}
	var count int
	if err := db.QueryRow(`SELECT count(*) FROM quiz_questions`).Scan(&count); err != nil || count != 0 {
		t.Fatalf("partial question survived: count=%d err=%v", count, err)
	}
}
func TestCallbackRetriesAreAtomicAndScoped(t *testing.T) {
	db := testutil.Database(t)
	testutil.SeedQuiz(t, db)
	repo := NewMicroLessonRepository(db)
	ctx := context.Background()
	job, err := repo.CreateJob(ctx, &models.MicroLessonJob{CourseID: 1, SectionID: sql.NullInt64{Int64: 1, Valid: true}, CreatedBy: 1, Language: "vi", Status: "queued", TargetMinutes: 5})
	if err != nil {
		t.Fatal(err)
	}
	body := dto.MicroLessonsCallback{JobID: job.ID, CourseID: 1, Lessons: []dto.MicroLessonGeneratedItem{{Title: "One", MarkdownContent: "Fixture", EstimatedMinutes: 5}}}
	var wg sync.WaitGroup
	for i := 0; i < 6; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := repo.SaveGeneratedLessons(ctx, &body); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()
	var count int
	if err := db.QueryRow(`SELECT count(*) FROM micro_lessons WHERE job_id=$1`, job.ID).Scan(&count); err != nil || count != 1 {
		t.Fatalf("duplicate lessons=%d err=%v", count, err)
	}
	body.CourseID = 2
	if err := repo.SaveGeneratedLessons(ctx, &body); !errors.Is(err, ErrCallbackConflict) {
		t.Fatalf("changed duplicate accepted: %v", err)
	}
	next, err := repo.CreateJob(ctx, &models.MicroLessonJob{CourseID: 1, CreatedBy: 1, Language: "vi", Status: "queued", TargetMinutes: 5})
	if err != nil {
		t.Fatal(err)
	}
	body.JobID = next.ID
	if err := repo.SaveGeneratedLessons(ctx, &body); !errors.Is(err, ErrCallbackScope) {
		t.Fatalf("cross-course callback accepted: %v", err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM lms_callback_receipts WHERE job_id=$1`, next.ID).Scan(&count); err != nil || count != 0 {
		t.Fatal("failed callback retained a receipt")
	}
}
func TestFileAccessUsesOwnerAndCourseScope(t *testing.T) {
	db := testutil.Database(t)
	testutil.SeedQuiz(t, db)
	repo := NewFileRepository(db)
	ctx := context.Background()
	if err := repo.Register(ctx, "document/private.pdf", 1, 100, false); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		user         int64
		read, manage bool
	}{{0, false, false}, {1, true, true}, {2, true, false}, {3, false, false}} {
		read, manage, err := repo.Access(ctx, "document/private.pdf", tc.user)
		if err != nil || read != tc.read || manage != tc.manage {
			t.Fatalf("user=%d read=%v manage=%v err=%v", tc.user, read, manage, err)
		}
	}
}

func TestStorageQuotaIsAtomicUnderConcurrentUploads(t *testing.T) {
	db := testutil.Database(t)
	repo := NewFileRepository(db, 100)
	ctx := context.Background()
	var wg sync.WaitGroup
	successes := make(chan string, 10)
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			key := fmt.Sprintf("document/quota-%d.pdf", index)
			err := repo.Register(ctx, key, 41, 30, false)
			if err == nil {
				successes <- key
			} else if !errors.Is(err, ErrFileQuota) {
				t.Error(err)
			}
		}(i)
	}
	wg.Wait()
	close(successes)
	var used int64
	if err := db.QueryRow(`SELECT COALESCE(SUM(size_bytes),0) FROM lms_file_assets WHERE owner_user_id=41`).Scan(&used); err != nil || used != 90 {
		t.Fatalf("used=%d err=%v", used, err)
	}
}

func TestAIFailureDoesNotBlockDurableLearningProgress(t *testing.T) {
	db := testutil.Database(t)
	testutil.SeedQuiz(t, db)
	ctx := context.Background()
	repo := NewQuizRepository(db)
	var attemptID int64
	if err := db.QueryRow(`INSERT INTO quiz_attempts(quiz_id,student_id,attempt_number,status) VALUES(1,2,1,'SUBMITTED') RETURNING id`).Scan(&attemptID); err != nil {
		t.Fatal(err)
	}
	if err := repo.EnqueueAttemptEffects(ctx, attemptID); err != nil {
		t.Fatal(err)
	}
	worked, err := repo.ProcessNextEffects(ctx, func(context.Context, QuizEffects) error { return errors.New("AI unavailable") })
	if !worked || err == nil {
		t.Fatal("failed delivery was not retained")
	}
	var completed bool
	var progress, attempts int
	if err := db.QueryRow(`SELECT completed_at IS NOT NULL,attempts FROM lms_quiz_effects WHERE attempt_id=$1`, attemptID).Scan(&completed, &attempts); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM content_progress WHERE content_id=1 AND student_id=2`).Scan(&progress); err != nil {
		t.Fatal(err)
	}
	if completed || attempts != 1 || progress != 1 {
		t.Fatalf("completed=%v retries=%d progress=%d", completed, attempts, progress)
	}
	if _, err := db.Exec(`UPDATE lms_quiz_effects SET available_at=now() WHERE attempt_id=$1`, attemptID); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.ProcessNextEffects(ctx, func(context.Context, QuizEffects) error { return nil }); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT completed_at IS NOT NULL FROM lms_quiz_effects WHERE attempt_id=$1`, attemptID).Scan(&completed); err != nil || !completed {
		t.Fatalf("completed=%v err=%v", completed, err)
	}
}
