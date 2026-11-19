package repository

import (
	"context"
	"fmt"

	"example/hello/internal/models"
)

// CreateQuestionWithAnswers owns one transaction for the entire aggregate.
func (r *QuizRepository) CreateQuestionWithAnswers(ctx context.Context, question *models.QuizQuestion, options []models.QuizAnswerOption, answers []models.QuizCorrectAnswer) error {
	aggregate := &models.QuestionWithOptions{QuizQuestion: *question, AnswerOptions: options, CorrectAnswers: answers}
	if err := r.CreateQuestionsWithAnswers(ctx, []*models.QuestionWithOptions{aggregate}); err != nil {
		return err
	}
	*question = aggregate.QuizQuestion
	return nil
}

// CreateQuestionsWithAnswers commits the batch as one aggregate: no partial import.
// Returned IDs/timestamps are populated in-place, avoiding a read per question.
func (r *QuizRepository) CreateQuestionsWithAnswers(ctx context.Context, questions []*models.QuestionWithOptions) error {
	tx, err := beginTransaction(ctx, r.db)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for index, question := range questions {
		if err := createQuestion(ctx, tx, &question.QuizQuestion); err != nil {
			return fmt.Errorf("create question at index %d: %w", index, err)
		}
		for i := range question.AnswerOptions {
			option := &question.AnswerOptions[i]
			option.QuestionID = question.ID
			if err := createAnswerOption(ctx, tx, option); err != nil {
				return fmt.Errorf("create option for question at index %d: %w", index, err)
			}
		}
		for i := range question.CorrectAnswers {
			answer := &question.CorrectAnswers[i]
			answer.QuestionID = question.ID
			if err := createCorrectAnswer(ctx, tx, answer); err != nil {
				return fmt.Errorf("create answer for question at index %d: %w", index, err)
			}
		}
	}
	return tx.Commit()
}
