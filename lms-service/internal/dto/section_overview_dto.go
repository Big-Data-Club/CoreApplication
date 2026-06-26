package dto

import "time"

// ── Request DTOs ──────────────────────────────────────────────────────────────

// GenerateSectionOverviewRequest is sent by the teacher to trigger generation.
type GenerateSectionOverviewRequest struct {
	Language      string `json:"language"`
	QuestionCount int    `json:"question_count"`
}

// UpdateOverviewLessonRequest allows the teacher to patch the draft lesson.
type UpdateOverviewLessonRequest struct {
	Title           *string                `json:"title"`
	MarkdownContent *string                `json:"markdown_content"`
	References      *[]OverviewReferenceItem `json:"references"`
}

// UpdateOverviewQuizRequest allows the teacher to patch the draft quiz questions.
type UpdateOverviewQuizRequest struct {
	Title     *string               `json:"title"`
	Questions *[]OverviewQuestion   `json:"questions"`
}

// PublishOverviewLessonRequest positions the lesson in a section after publishing.
type PublishOverviewLessonRequest struct {
	SectionID  int64 `json:"section_id"  binding:"required"`
	OrderIndex int   `json:"order_index"`
}

// PublishOverviewQuizRequest positions the quiz in a section after publishing.
type PublishOverviewQuizRequest struct {
	SectionID        int64 `json:"section_id"         binding:"required"`
	OrderIndex       int   `json:"order_index"`
	TimeLimitMinutes int   `json:"time_limit_minutes"`
}

// ── Shared sub-types ──────────────────────────────────────────────────────────

// OverviewReferenceItem is a content item referenced by the lesson or quiz.
type OverviewReferenceItem struct {
	ContentID   int64  `json:"content_id"`
	Title       string `json:"title"`
	ContentType string `json:"content_type"`
}

// OverviewQuestionOption is a single MCQ option inside an overview question.
type OverviewQuestionOption struct {
	Text      string `json:"text"`
	IsCorrect bool   `json:"is_correct"`
}

// OverviewQuestion is one generated quiz question.
type OverviewQuestion struct {
	Question           string                   `json:"question"`
	Options            []OverviewQuestionOption `json:"options"`
	Explanation        string                   `json:"explanation"`
	BloomLevel         string                   `json:"bloom_level"`
	ReferenceContentIDs []int64                 `json:"reference_content_ids"`
}

// ── Response DTOs ─────────────────────────────────────────────────────────────

// SectionOverviewJobResponse is the serialized form of a section_overview_jobs row.
type SectionOverviewJobResponse struct {
	ID            int64     `json:"id"`
	SectionID     int64     `json:"section_id"`
	CourseID      int64     `json:"course_id"`
	Status        string    `json:"status"`
	Progress      int       `json:"progress"`
	Stage         string    `json:"stage"`
	ErrorMsg      string    `json:"error_msg"`
	Language      string    `json:"language"`
	QuestionCount int       `json:"question_count"`
	Logs          string    `json:"logs"`
	CreatedBy     int64     `json:"created_by"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// SectionOverviewLessonResponse is the serialized form of a section_overview_lessons row.
type SectionOverviewLessonResponse struct {
	ID                int64                  `json:"id"`
	JobID             int64                  `json:"job_id"`
	SectionID         int64                  `json:"section_id"`
	CourseID          int64                  `json:"course_id"`
	Title             string                 `json:"title"`
	Summary           string                 `json:"summary"`
	MarkdownContent   string                 `json:"markdown_content"`
	References        []OverviewReferenceItem `json:"references"`
	Status            string                 `json:"status"`
	PublishedContentID *int64               `json:"published_content_id"`
	CreatedBy         int64                  `json:"created_by"`
	CreatedAt         time.Time              `json:"created_at"`
	UpdatedAt         time.Time              `json:"updated_at"`
}

// SectionOverviewQuizResponse is the serialized form of a section_overview_quizzes row.
type SectionOverviewQuizResponse struct {
	ID              int64                  `json:"id"`
	JobID           int64                  `json:"job_id"`
	SectionID       int64                  `json:"section_id"`
	CourseID        int64                  `json:"course_id"`
	Title           string                 `json:"title"`
	Summary         string                 `json:"summary"`
	QuestionCount   int                    `json:"question_count"`
	Questions       []OverviewQuestion     `json:"questions"`
	References      []OverviewReferenceItem `json:"references"`
	Status          string                 `json:"status"`
	PublishedQuizID *int64                 `json:"published_quiz_id"`
	CreatedBy       int64                  `json:"created_by"`
	CreatedAt       time.Time              `json:"created_at"`
	UpdatedAt       time.Time              `json:"updated_at"`
}

// SectionOverviewJobDetailResponse wraps a job with its lesson and quiz.
type SectionOverviewJobDetailResponse struct {
	Job    SectionOverviewJobResponse     `json:"job"`
	Lesson *SectionOverviewLessonResponse `json:"lesson"`
	Quiz   *SectionOverviewQuizResponse   `json:"quiz"`
}

// ── Internal callback DTOs (AI service -> LMS) ─────────────────────────────────

// SectionOverviewCallbackStatus carries progress updates from the AI service.
type SectionOverviewCallbackStatus struct {
	JobID    int64  `json:"job_id"`
	Status   string `json:"status"`
	Progress int    `json:"progress"`
	Stage    string `json:"stage"`
	Error    string `json:"error"`
	Logs     string `json:"logs"`
}

// SectionOverviewCallbackResultsLesson is the lesson payload inside the result callback.
type SectionOverviewCallbackResultsLesson struct {
	Title           string                 `json:"title"`
	Summary         string                 `json:"summary"`
	MarkdownContent string                 `json:"markdown_content"`
	References      []OverviewReferenceItem `json:"references"`
}

// SectionOverviewCallbackResultsQuiz is the quiz payload inside the result callback.
type SectionOverviewCallbackResultsQuiz struct {
	Title         string                 `json:"title"`
	Summary       string                 `json:"summary"`
	QuestionCount int                    `json:"question_count"`
	Questions     []OverviewQuestion     `json:"questions"`
	References    []OverviewReferenceItem `json:"references"`
}

// SectionOverviewCallbackResults is the full result payload posted by the AI service
// when generation is complete.
type SectionOverviewCallbackResults struct {
	JobID     int64                                `json:"job_id"`
	SectionID int64                                `json:"section_id"`
	CourseID  int64                                `json:"course_id"`
	Language  string                               `json:"language"`
	Lesson    SectionOverviewCallbackResultsLesson `json:"lesson"`
	Quiz      SectionOverviewCallbackResultsQuiz   `json:"quiz"`
}
