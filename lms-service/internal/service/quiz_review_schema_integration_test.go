package service

import (
	"context"
	"errors"
	"testing"

	"example/hello/internal/repository"
)

// Installs every real migration, including the assessment snapshot columns.
// The narrow reporting fixture alone cannot detect SELECT */Scan mismatches.
func TestQuizReviewAfterAssessmentMigration(t *testing.T) {
	s, db := quizFixture(t)
	ctx := context.Background()
	questions, err := s.BatchCreateQuestions(ctx, 1, batchQuestions(1), 1, "TEACHER")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(`UPDATE quizzes SET show_results_immediately=true,allow_review=true,show_correct_answers=true,show_feedback=true WHERE id=1`); err != nil {
		t.Fatal(err)
	}
	var attemptID, answerID int64
	if err = db.QueryRow(`INSERT INTO quiz_attempts(quiz_id,student_id,attempt_number,status,submitted_at,total_points,earned_points,percentage,is_passed)
 VALUES(1,2,1,'GRADED',now(),1,1,100,true) RETURNING id`).Scan(&attemptID); err != nil {
		t.Fatal(err)
	}
	if err = db.QueryRow(`INSERT INTO quiz_student_answers(attempt_id,question_id,answer_data,points_earned,is_correct,grader_feedback)
 VALUES($1,$2,'{"selected_option_id":1}',1,true,'**Correct**') RETURNING id`, attemptID, questions[0].ID).Scan(&answerID); err != nil {
		t.Fatal(err)
	}
	repo := repository.NewQuizRepository(db)
	if answer, err := repo.GetStudentAnswer(ctx, answerID); err != nil {
		t.Errorf("read answer after migration: %v", err)
	} else if answer.ID != answerID {
		t.Error("wrong answer")
	}
	if answer, err := repo.GetStudentAnswerByQuestion(ctx, attemptID, questions[0].ID); err != nil {
		t.Errorf("read answer by question after migration: %v", err)
	} else if answer == nil || answer.ID != answerID {
		t.Error("lost answer")
	}
	review, err := s.ReviewQuiz(ctx, attemptID, 2)
	if err != nil {
		t.Errorf("student review after migration: %v", err)
	} else if len(review.QuestionsWithAnswers) != 1 || review.QuestionsWithAnswers[0].StudentAnswer == nil {
		t.Error("lost reviewed answer")
	} else {
		answer := review.QuestionsWithAnswers[0].StudentAnswer
		if answer.PointsEarned == nil || *answer.PointsEarned != 1 || answer.IsCorrect == nil || !*answer.IsCorrect || answer.GraderFeedback != "**Correct**" {
			t.Error("score, correctness or feedback was read into the wrong field")
		}
	}
	if _, err = s.GetQuizResult(ctx, attemptID, 2); err != nil {
		t.Errorf("student result after migration: %v", err)
	}
	if _, err = s.ReviewQuiz(ctx, attemptID, 3); !errors.Is(err, ErrQuizAccess) {
		t.Fatalf("foreign student accessed review: %v", err)
	}
}
