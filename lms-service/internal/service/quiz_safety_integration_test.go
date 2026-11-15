package service

import (
	"context"
	"database/sql"
	"sync"
	"testing"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/internal/testutil"
)

func quizFixture(t *testing.T) (*QuizService, *sql.DB) {
	t.Helper()
	db := testutil.Database(t)
	testutil.SeedQuiz(t, db)
	repo := repository.NewQuizRepository(db)
	return NewQuizService(repo, repository.NewCourseRepository(db), repository.NewUserRepository(db), repository.NewProgressRepository(db), nil, nil), db
}
func TestConcurrentQuizStartResumeAndSubmit(t *testing.T) {
	s, db := quizFixture(t)
	ctx := context.Background()
	var wg sync.WaitGroup
	ids := make(chan int64, 12)
	failures := make(chan error, 12)
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			attempt, err := s.StartQuizAttempt(ctx, 1, 2, "", "fixture")
			if err != nil {
				failures <- err
			} else {
				ids <- attempt.ID
			}
		}()
	}
	wg.Wait()
	close(ids)
	close(failures)
	for err := range failures {
		t.Errorf("start failed: %v", err)
	}
	var id int64
	for actual := range ids {
		if id != 0 && actual != id {
			t.Fatal("concurrent starts created distinct active attempts")
		}
		id = actual
	}
	if id == 0 {
		t.Fatal("no active attempt")
	}
	// The maximum attempt count is one; reloading must still resume that attempt.
	if _, err := s.StartQuizAttempt(ctx, 1, 2, "", ""); err != nil {
		t.Fatal("cannot resume final allowed attempt:", err)
	}
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			result, err := s.SubmitQuiz(ctx, id, 2)
			if err != nil {
				t.Errorf("submit: %v", err)
			} else if result.Attempt.EarnedPoints != nil || len(result.StudentAnswers) > 0 {
				t.Error("hidden result leaked")
			}
		}()
	}
	wg.Wait()
	var count int
	if err := db.QueryRow(`SELECT count(*) FROM lms_quiz_effects WHERE attempt_id=$1`, id).Scan(&count); err != nil || count != 1 {
		t.Fatalf("outbox=%d err=%v", count, err)
	}
	if _, err := s.SubmitAnswer(ctx, &dto.SubmitAnswerRequest{AttemptID: id, QuestionID: 1, AnswerData: map[string]interface{}{}}, 2); err == nil {
		t.Fatal("answer accepted after submit")
	}
}
func TestQuizAccessAndAnswerRedaction(t *testing.T) {
	s, db := quizFixture(t)
	ctx := context.Background()
	if _, err := s.ListQuestions(ctx, 1, 3, "TEACHER", true); err == nil {
		t.Fatal("unrelated teacher can read answer key")
	}
	if _, err := s.StartQuizAttempt(ctx, 1, 3, "", ""); err == nil {
		t.Fatal("non-member can attempt quiz")
	}
	question := &models.QuizQuestion{QuizID: 1, QuestionType: models.QuestionTypeSingleChoice, QuestionText: "Fixture?", Points: 10, OrderIndex: 1, Settings: []byte(`{}`)}
	if err := s.quizRepo.CreateQuestionWithAnswers(ctx, question, []models.QuizAnswerOption{{OptionText: "Yes", IsCorrect: true, OrderIndex: 1}}, nil); err != nil {
		t.Fatal(err)
	}
	var optionID int64
	if err := db.QueryRow(`SELECT id FROM quiz_answer_options WHERE question_id=$1`, question.ID).Scan(&optionID); err != nil {
		t.Fatal(err)
	}
	attempt, err := s.StartQuizAttempt(ctx, 1, 2, "", "")
	if err != nil {
		t.Fatal(err)
	}
	response, err := s.SubmitAnswer(ctx, &dto.SubmitAnswerRequest{AttemptID: attempt.ID, QuestionID: question.ID, AnswerData: map[string]interface{}{"selected_option_id": optionID}}, 2)
	if err != nil {
		t.Fatal(err)
	}
	if response.IsCorrect != nil || response.PointsEarned != nil {
		t.Fatal("answer correctness leaked before submission")
	}
	if _, err := s.GetAttemptAnswers(ctx, attempt.ID, 3); err != ErrQuizAccess {
		t.Fatalf("cross-user answers access: %v", err)
	}
	answers, err := s.GetAttemptAnswers(ctx, attempt.ID, 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(answers) != 1 || answers[0].IsCorrect.Valid {
		t.Fatal("resume answers leak correctness")
	}
	if _, err := s.SubmitQuiz(ctx, attempt.ID, 2); err != nil {
		t.Fatal(err)
	}
	grade := &dto.GradeAnswerRequest{AnswerID: answers[0].ID, PointsEarned: 5, GraderFeedback: "Fixture feedback"}
	if err := s.GradeAnswer(ctx, grade, 1, "TEACHER"); err != nil {
		t.Fatal(err)
	}
	first, err := s.quizRepo.GetStudentAnswer(ctx, grade.AnswerID)
	if err != nil {
		t.Fatal(err)
	}
	if err := s.GradeAnswer(ctx, grade, 1, "TEACHER"); err != nil {
		t.Fatal(err)
	}
	second, err := s.quizRepo.GetStudentAnswer(ctx, grade.AnswerID)
	if err != nil {
		t.Fatal(err)
	}
	if !first.GradedAt.Time.Equal(second.GradedAt.Time) {
		t.Fatal("duplicate manual grade produced a new review delivery")
	}

}

func TestCourseCannotAttachAnotherOwnersPrivateFile(t *testing.T) {
	_, db := quizFixture(t)
	ctx := context.Background()
	files := repository.NewFileRepository(db)
	if err := files.Register(ctx, "document/private.pdf", 1, 100, false); err != nil {
		t.Fatal(err)
	}
	_, err := db.Exec(`INSERT INTO courses(id,title,status,created_by,visibility,org_id) VALUES(2,'Other','PUBLISHED',3,'ORG_ONLY',(SELECT id FROM organizations WHERE slug='bdc'));
 INSERT INTO course_sections(id,course_id,title,order_index,is_published) VALUES(2,2,'Chapter',1,true);`)
	if err != nil {
		t.Fatal(err)
	}
	courses := NewCourseService(repository.NewCourseRepository(db), repository.NewUserRepository(db), repository.NewEnrollmentRepository(db), repository.NewOrganizationRepository(db), nil, nil, NewFileAccessService(files))
	_, err = courses.CreateContent(ctx, 2, &dto.CreateContentRequest{Type: "DOCUMENT", Title: "Guessed attachment", OrderIndex: 1, Metadata: map[string]interface{}{"file_path": "document/private.pdf"}}, 3, "TEACHER")
	if err != ErrFileAccess {
		t.Fatalf("private attachment claim was accepted: %v", err)
	}
}

func TestConcurrentAnswersAndSubmitHaveConsistentFinalScore(t *testing.T) {
	s, db := quizFixture(t)
	ctx := context.Background()
	question := &models.QuizQuestion{QuizID: 1, QuestionType: models.QuestionTypeSingleChoice, QuestionText: "Concurrent?", Points: 10, OrderIndex: 1, Settings: []byte(`{}`)}
	if err := s.quizRepo.CreateQuestionWithAnswers(ctx, question, []models.QuizAnswerOption{{OptionText: "Yes", IsCorrect: true, OrderIndex: 1}}, nil); err != nil {
		t.Fatal(err)
	}
	var optionID int64
	if err := db.QueryRow(`SELECT id FROM quiz_answer_options WHERE question_id=$1`, question.ID).Scan(&optionID); err != nil {
		t.Fatal(err)
	}
	attempt, err := s.StartQuizAttempt(ctx, 1, 2, "", "")
	if err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			<-start
			if index%4 == 0 {
				if _, err := s.SubmitQuiz(ctx, attempt.ID, 2); err != nil {
					t.Error(err)
				}
			} else {
				_, _ = s.SubmitAnswer(ctx, &dto.SubmitAnswerRequest{AttemptID: attempt.ID, QuestionID: question.ID, AnswerData: map[string]interface{}{"selected_option_id": optionID}}, 2)
			}
		}(i)
	}
	close(start)
	wg.Wait()
	var score, answers float64
	if err := db.QueryRow(`SELECT COALESCE(qa.earned_points,0),COALESCE((SELECT SUM(a.points_earned) FROM quiz_student_answers a WHERE a.attempt_id=qa.id),0) FROM quiz_attempts qa WHERE qa.id=$1`, attempt.ID).Scan(&score, &answers); err != nil {
		t.Fatal(err)
	}
	if score != answers {
		t.Fatalf("late answer diverged from finalized score: score=%v answers=%v", score, answers)
	}
}
