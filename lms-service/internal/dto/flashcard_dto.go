package dto

import "time"

// Flashcards

// GenerateFlashcardsRequest represents requesting AI to generate flashcards for a specific weak node
type GenerateFlashcardsRequest struct {
	Count     int    `json:"count" binding:"required,min=1,max=10"`
	LessonID  *int64 `json:"lesson_id,omitempty"`
	ContentID *int64 `json:"content_id,omitempty"`
	TextChunk string `json:"text_chunk,omitempty"`
}

// BulkSaveFlashcardsRequest represents requesting AI to save pre-generated flashcards
type BulkSaveFlashcardsRequest struct {
	NodeID     *int64                   `json:"node_id,omitempty"`
	LessonID   *int64                   `json:"lesson_id,omitempty"`
	ContentID  *int64                   `json:"content_id,omitempty"`
	Flashcards []map[string]interface{} `json:"flashcards" binding:"required"`
}

// FlashcardResponse represents a single flashcard
type FlashcardResponse struct {
	ID                int64      `json:"id"`
	CourseID          int64      `json:"course_id"`
	NodeID            *int64     `json:"node_id"`
	LessonID          *int64     `json:"lesson_id,omitempty"`
	ContentID         *int64     `json:"content_id,omitempty"`
	FrontText         string     `json:"front_text"`
	BackText          string     `json:"back_text"`
	SourceDiagnosisID *int64     `json:"source_diagnosis_id,omitempty"`
	Status            string     `json:"status"`
	NextReviewDate    *time.Time `json:"next_review_date,omitempty"`
	CreatedAt         time.Time  `json:"created_at"`
	// SM-2 repetition metadata (included when listing all flashcards for review)
	EasinessFactor *float64   `json:"easiness_factor,omitempty"`
	IntervalDays   *int       `json:"interval_days,omitempty"`
	Repetitions    *int       `json:"repetitions,omitempty"`
	LastReviewedAt *time.Time `json:"last_reviewed_at,omitempty"`
}

// ReviewFlashcardRequest represents the student's self-assessed quality of recalling the flashcard
type ReviewFlashcardRequest struct {
	Quality int `json:"quality" binding:"required,min=0,max=5"`
	// 0: Complete blackout
	// 1: Incorrect, but remembered the correct one upon seeing it
	// 2: Incorrect, where the correct one seemed easy to recall
	// 3: Correct, but required significant effort
	// 4: Correct, after hesitation
	// 5: Correct, perfect response
}

// ReviewFlashcardResponse returns the updated SM-2 stats
type ReviewFlashcardResponse struct {
	FlashcardID    int64      `json:"flashcard_id"`
	EasinessFactor float64    `json:"easiness_factor"`
	IntervalDays   int        `json:"interval_days"`
	Repetitions    int        `json:"repetitions"`
	NextReviewDate time.Time  `json:"next_review_date"`
}
