package repository

import (
	"context"

	"example/hello/internal/models"
)

// CreateQuestionWithAnswers owns one transaction for the entire aggregate.
func (r *QuizRepository) CreateQuestionWithAnswers(ctx context.Context, question *models.QuizQuestion, options []models.QuizAnswerOption, answers []models.QuizCorrectAnswer) error {
	tx, err := beginTransaction(ctx, r.db)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if err := createQuestion(ctx, tx, question); err != nil {
		return err
	}
	for i := range options {
		options[i].QuestionID = question.ID
		if err := createAnswerOption(ctx, tx, &options[i]); err != nil {
			return err
		}
	}
	for i := range answers {
		answers[i].QuestionID = question.ID
		if err := createCorrectAnswer(ctx, tx, &answers[i]); err != nil {
			return err
		}
	}
	return tx.Commit()
}
