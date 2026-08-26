// lms-service/internal/models/question_bank.go
package models

import (
	"database/sql"
	"time"
)

// Question bank provenance.
const (
	BankSourceManual      = "MANUAL"
	BankSourceImport      = "IMPORT"
	BankSourceAIGenerated = "AI_GENERATED"
	BankSourceQuiz        = "QUIZ" // synced from a live quiz question
)

// Question bank review status.
const (
	BankStatusDraft    = "DRAFT"
	BankStatusApproved = "APPROVED"
	BankStatusDisabled = "DISABLED"
)

// QuestionBankItem is a reusable, classified question owned by a course.
// Answer options / correct answers / settings mirror the quiz question
// contracts (JSONB) so promotion into a quiz is a pure copy.
type QuestionBankItem struct {
	ID             int64            `json:"id" db:"id"`
	CourseID       int64            `json:"course_id" db:"course_id"`
	NodeID         sql.NullInt64    `json:"node_id" db:"node_id"`
	SourceQuizID   sql.NullInt64    `json:"source_quiz_id" db:"source_quiz_id"`
	QuestionType   string           `json:"question_type" db:"question_type"`
	QuestionText   string           `json:"question_text" db:"question_text"`
	Explanation    sql.NullString   `json:"explanation" db:"explanation"`
	Points         float64          `json:"points" db:"points"`
	BloomLevel     sql.NullString   `json:"bloom_level" db:"bloom_level"`
	Difficulty     string           `json:"difficulty" db:"difficulty"`
	AnswerOptions  []byte           `json:"-" db:"answer_options"`   // JSONB
	CorrectAnswers []byte           `json:"-" db:"correct_answers"`  // JSONB
	Settings       []byte           `json:"-" db:"settings"`         // JSONB
	Tags           []string         `json:"tags" db:"tags"`
	Source         string           `json:"source" db:"source"`
	Status         string           `json:"status" db:"status"`
	CreatedBy      int64            `json:"created_by" db:"created_by"`
	CreatedAt      time.Time        `json:"created_at" db:"created_at"`
	UpdatedAt      time.Time        `json:"updated_at" db:"updated_at"`

	// Joined display fields (optional).
	NodeName sql.NullString `json:"node_name,omitempty" db:"-"`
}

func (q *QuestionBankItem) AnswerOptionsRaw() []byte  { return q.AnswerOptions }
func (q *QuestionBankItem) CorrectAnswersRaw() []byte { return q.CorrectAnswers }
func (q *QuestionBankItem) SettingsRaw() []byte       { return q.Settings }
