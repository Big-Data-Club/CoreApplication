package dto

import "encoding/json"

// ── Requests from frontend ───────────────────────────────────────────

type GenerateMicroQuizzesRequest struct {
	ContentID  int64  `json:"content_id"`
	YouTubeURL string `json:"youtube_url,omitempty"`
	SectionID  *int64 `json:"section_id,omitempty"`
	Language   string `json:"language"`
}

type UpdateMicroQuizRequest struct {
	Title         string          `json:"title" binding:"required"`
	Summary       string          `json:"summary"`
	QuestionsJSON json.RawMessage `json:"questions_json" binding:"required"`
	OrderIndex    int             `json:"order_index"`
}

type PublishMicroQuizRequest struct {
	SectionID  int64 `json:"section_id" binding:"required"`
	OrderIndex int   `json:"order_index"`
}

// ── Internal callback payloads (AI service -> LMS) ────────────────────

type MicroQuizStatusCallback struct {
	JobID        int64  `json:"job_id" binding:"required"`
	Status       string `json:"status" binding:"required"`
	Progress     int    `json:"progress"`
	Stage        string `json:"stage"`
	QuizzesCount int    `json:"quizzes_count"`
	Error        string `json:"error"`
}

// MicroQuizQuestionItem represents a single question within the structured JSON.
// Used by both AI callback and frontend editing.
type MicroQuizQuestionItem struct {
	Question   string                     `json:"question"`
	Options    []MicroQuizQuestionOption   `json:"options"`
	Explanation string                    `json:"explanation"`
	BloomLevel string                     `json:"bloom_level"`
}

type MicroQuizQuestionOption struct {
	Text      string `json:"text"`
	IsCorrect bool   `json:"is_correct"`
}

type MicroQuizGeneratedItem struct {
	Title          string          `json:"title"`
	Summary        string          `json:"summary"`
	QuestionsJSON  json.RawMessage `json:"questions_json"`
	QuestionsCount int             `json:"questions_count"`
	OrderIndex     int             `json:"order_index"`
	NodeID         *int64          `json:"node_id"`
}

type MicroQuizzesCallback struct {
	JobID           int64                    `json:"job_id" binding:"required"`
	CourseID        int64                    `json:"course_id" binding:"required"`
	SectionID       *int64                   `json:"section_id"`
	SourceContentID *int64                   `json:"source_content_id"`
	Language        string                   `json:"language"`
	Quizzes         []MicroQuizGeneratedItem `json:"quizzes" binding:"required"`
}
