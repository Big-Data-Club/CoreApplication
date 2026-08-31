// lms-service/internal/dto/question_bank_dto.go
package dto

import (
	"encoding/json"
	"time"
)

// ── Requests ──────────────────────────────────────────────────────────────────

// CreateBankItemsRequest bulk-inserts up to 100 items in one call
// (AI generation batches + document imports).
type CreateBankItemsRequest struct {
	Items []CreateBankItemRequest `json:"items" binding:"required,min=1,max=100"`
}

type CreateBankItemRequest struct {
	NodeID         *int64                       `json:"node_id"`
	QuestionType   QuestionType                 `json:"question_type" binding:"required"`
	QuestionText   string                       `json:"question_text" binding:"required,min=3,max=10000"`
	Explanation    string                       `json:"explanation"`
	Points         *float64                     `json:"points"`      // default 10
	BloomLevel     string                       `json:"bloom_level"` // optional; validated against BloomLevels
	Difficulty     string                       `json:"difficulty"`  // default MEDIUM
	AnswerOptions  []CreateAnswerOptionRequest  `json:"answer_options"`
	CorrectAnswers []CreateCorrectAnswerRequest `json:"correct_answers"`
	Settings       map[string]interface{}       `json:"settings"`
	Tags           []string                     `json:"tags"`
	Source         string                       `json:"source"` // default MANUAL; IMPORT/AI_GENERATED set by callers
	Status         string                       `json:"status"` // default APPROVED
}

// UpdateBankItemRequest - partial update (all optional).
type UpdateBankItemRequest struct {
	NodeID         *int64           `json:"node_id"` // null clears the link (dangling)
	ClearNode      bool             `json:"clear_node"`
	QuestionText   *string          `json:"question_text"`
	Difficulty     string           `json:"difficulty"`
	BloomLevel     *string          `json:"bloom_level"`
	Points         *float64         `json:"points"`
	Status         *string          `json:"status"`
	Tags           *[]string        `json:"tags"`
	Explanation    *string          `json:"explanation"`
	// Raw JSON keeps PATCH semantics: omitted is distinct from an intentional
	// empty array, and repository code sends it as text rather than bytea.
	AnswerOptions  *json.RawMessage `json:"answer_options"`
	CorrectAnswers *json.RawMessage `json:"correct_answers"`
}

// BankListQuery - filter/sort/pagination for GET list.
// Embeds PaginationRequest (page, page_size) consistent with the codebase.
type BankListQuery struct {
	PaginationRequest
	Difficulty string `form:"difficulty"`  // EASY|MEDIUM|HARD|"" (all)
	BloomLevel string `form:"bloom_level"` // remember..create|""
	NodeID     *int64 `form:"node_id"`     // exact node
	Dangling   bool   `form:"dangling"`    // true -> node_id IS NULL
	Source     string `form:"source"`      // MANUAL|IMPORT|AI_GENERATED|""
	Status     string `form:"status"`      // default: all except DISABLED handled by service
	TimeFrom   string `form:"time_from"`   // RFC3339 or YYYY-MM-DD
	TimeTo     string `form:"time_to"`
	Q          string `form:"q"`     // full-text search
	Sort       string `form:"sort"`  // created_at|points|difficulty (default created_at)
	Order      string `form:"order"` // asc|desc (default desc)
}

// CreateQuizFromBankRequest assembles a quiz shell from selected bank items.
type CreateQuizFromBankRequest struct {
	// SectionID is preferred: the LMS creates the QUIZ content and quiz in one
	// operation. ContentID remains supported for older clients.
	SectionID        int64      `json:"section_id"`
	ContentID        int64      `json:"content_id"`
	Title            string     `json:"title" binding:"required,min=3,max=500"`
	Description      string     `json:"description"`
	Instructions     string     `json:"instructions"`
	TimeLimitMinutes *int       `json:"time_limit_minutes"`
	AvailableFrom    *time.Time `json:"available_from"`
	AvailableUntil   *time.Time `json:"available_until"`
	MaxAttempts      *int       `json:"max_attempts"`
	PassingScore     *float64   `json:"passing_score"`
	TotalPoints      *float64   `json:"total_points"` // default: sum of item points
	ItemIDs          []int64    `json:"item_ids" binding:"required,min=1,max=200"`
	ShuffleQuestions bool       `json:"shuffle_questions"`
	ShuffleAnswers   bool       `json:"shuffle_answers"`
	AutoGrade        bool       `json:"auto_grade"`
	IsPublished      bool       `json:"is_published"`
	// KeepItemsInBank always true by design: bank items are copied into the
	// quiz, never moved.
}

type SuggestQuizMetadataRequest struct {
	ItemIDs []int64 `json:"item_ids" binding:"required,min=1,max=50"`
}

type SuggestQuizMetadataResponse struct {
	Title        string `json:"title"`
	Description  string `json:"description"`
	Instructions string `json:"instructions"`
}

// ── Responses ─────────────────────────────────────────────────────────────────

type BankItemResponse struct {
	ID             int64           `json:"id"`
	CourseID       int64           `json:"course_id"`
	NodeID         *int64          `json:"node_id"`
	NodeName       string          `json:"node_name,omitempty"`
	SourceQuizID   *int64          `json:"source_quiz_id,omitempty"`
	QuestionType   string          `json:"question_type"`
	QuestionText   string          `json:"question_text"`
	Explanation    string          `json:"explanation,omitempty"`
	Points         float64         `json:"points"`
	BloomLevel     string          `json:"bloom_level,omitempty"`
	Difficulty     string          `json:"difficulty"`
	AnswerOptions  json.RawMessage `json:"answer_options"`
	CorrectAnswers json.RawMessage `json:"correct_answers"`
	Settings       json.RawMessage `json:"settings"`
	Tags           []string        `json:"tags"`
	Source         string          `json:"source"`
	Status         string          `json:"status"`
	CreatedBy      int64           `json:"created_by"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
}

type BankListResponse struct {
	Items      []BankItemResponse `json:"items"`
	Page       int                `json:"page"`
	PageSize   int                `json:"page_size"`
	Total      int64              `json:"total"`
	TotalPages int                `json:"total_pages"`
}

// BankStatsResponse - facet counts for the library header/chips.
type BankStatsResponse struct {
	Total         int64            `json:"total"`
	ByDifficulty  map[string]int64 `json:"by_difficulty"`
	ByBloom       map[string]int64 `json:"by_bloom"`
	BySource      map[string]int64 `json:"by_source"`
	DanglingCount int64            `json:"dangling_count"`
	ByMonth       []BankMonthCount `json:"by_month"`
}

type BankMonthCount struct {
	Month string `json:"month"` // YYYY-MM
	Count int64  `json:"count"`
}

// CreateQuizFromBankResponse mirrors a quiz creation result.
type CreateQuizFromBankResponse struct {
	QuizID         int64 `json:"quiz_id"`
	ContentID      int64 `json:"content_id"`
	QuestionsAdded int   `json:"questions_added"`
	IsPublished    bool  `json:"is_published"`
}
