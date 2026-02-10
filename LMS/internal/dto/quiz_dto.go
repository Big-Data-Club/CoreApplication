package dto

import "time"

// QuestionImage represents an image attached to a question
type QuestionImage struct {
	ID           string    `json:"id"`                      // Unique image ID
	URL          string    `json:"url"`                     // Public URL to access image
	FilePath     string    `json:"file_path"`               // Storage path
	FileName     string    `json:"file_name"`               // Original filename
	FileSize     int64     `json:"file_size"`               // Size in bytes
	MimeType     string    `json:"mime_type"`               // e.g., "image/png"
	Position     string    `json:"position"`                // "above_question", "below_question", "inline"
	Caption      string    `json:"caption,omitempty"`       // Optional caption
	AltText      string    `json:"alt_text,omitempty"`      // Accessibility text
	Width        int       `json:"width,omitempty"`         // Original width in pixels
	Height       int       `json:"height,omitempty"`        // Original height in pixels
	DisplayWidth string    `json:"display_width,omitempty"` // CSS width (e.g., "100%", "500px")
	CreatedAt    time.Time `json:"created_at"`
}

// AnswerOptionImage represents an image for an answer option
type AnswerOptionImage struct {
	URL      string `json:"url"`
	FilePath string `json:"file_path"`
	FileName string `json:"file_name"`
	FileSize int64  `json:"file_size"`
	MimeType string `json:"mime_type"`
	AltText  string `json:"alt_text,omitempty"`
}

// ImageConfig represents image configuration for a quiz
type ImageConfig struct {
	MaxImages       int    `json:"max_images"`
	AllowZoom       bool   `json:"allow_zoom"`
	DefaultPosition string `json:"default_position"`
}

// ============================================
// QUIZ DTOs
// ============================================

// CreateQuizRequest represents request to create a quiz
type CreateQuizRequest struct {
	ContentID              int64      `json:"content_id" binding:"required"`
	Title                  string     `json:"title" binding:"required,min=3,max=500"`
	Description            string     `json:"description"`
	Instructions           string     `json:"instructions"`
	TimeLimitMinutes       *int       `json:"time_limit_minutes"`
	AvailableFrom          *time.Time `json:"available_from"`
	AvailableUntil         *time.Time `json:"available_until"`
	MaxAttempts            *int       `json:"max_attempts"`
	ShuffleQuestions       bool       `json:"shuffle_questions"`
	ShuffleAnswers         bool       `json:"shuffle_answers"`
	PassingScore           *float64   `json:"passing_score"`
	TotalPoints            float64    `json:"total_points" binding:"required,min=0"`
	AutoGrade              bool       `json:"auto_grade"`
	ShowResultsImmediately bool       `json:"show_results_immediately"`
	ShowCorrectAnswers     bool       `json:"show_correct_answers"`
	AllowReview            bool       `json:"allow_review"`
	ShowFeedback           bool       `json:"show_feedback"`
}

// UpdateQuizRequest represents request to update quiz
type UpdateQuizRequest struct {
	Title                  *string    `json:"title" binding:"omitempty,min=3,max=500"`
	Description            *string    `json:"description"`
	Instructions           *string    `json:"instructions"`
	TimeLimitMinutes       *int       `json:"time_limit_minutes"`
	AvailableFrom          *time.Time `json:"available_from"`
	AvailableUntil         *time.Time `json:"available_until"`
	MaxAttempts            *int       `json:"max_attempts"`
	ShuffleQuestions       *bool      `json:"shuffle_questions"`
	ShuffleAnswers         *bool      `json:"shuffle_answers"`
	PassingScore           *float64   `json:"passing_score"`
	TotalPoints            *float64   `json:"total_points"`
	AutoGrade              *bool      `json:"auto_grade"`
	ShowResultsImmediately *bool      `json:"show_results_immediately"`
	ShowCorrectAnswers     *bool      `json:"show_correct_answers"`
	AllowReview            *bool      `json:"allow_review"`
	ShowFeedback           *bool      `json:"show_feedback"`
	IsPublished            *bool      `json:"is_published"`
}

// QuizResponse represents quiz details
type QuizResponse struct {
	ID                     int64      `json:"id"`
	ContentID              int64      `json:"content_id"`
	Title                  string     `json:"title"`
	Description            string     `json:"description,omitempty"`
	Instructions           string     `json:"instructions,omitempty"`
	TimeLimitMinutes       *int       `json:"time_limit_minutes,omitempty"`
	AvailableFrom          *time.Time `json:"available_from,omitempty"`
	AvailableUntil         *time.Time `json:"available_until,omitempty"`
	MaxAttempts            *int       `json:"max_attempts,omitempty"`
	ShuffleQuestions       bool       `json:"shuffle_questions"`
	ShuffleAnswers         bool       `json:"shuffle_answers"`
	PassingScore           *float64   `json:"passing_score,omitempty"`
	TotalPoints            float64    `json:"total_points"`
	AutoGrade              bool       `json:"auto_grade"`
	ShowResultsImmediately bool       `json:"show_results_immediately"`
	ShowCorrectAnswers     bool       `json:"show_correct_answers"`
	AllowReview            bool       `json:"allow_review"`
	ShowFeedback           bool       `json:"show_feedback"`
	IsPublished            bool       `json:"is_published"`
	CreatedBy              int64      `json:"created_by"`
	CreatorName            string     `json:"creator_name,omitempty"`
	CreatorEmail           string     `json:"creator_email,omitempty"`
	CreatedAt              time.Time  `json:"created_at"`
	UpdatedAt              time.Time  `json:"updated_at"`

	// Additional stats (optional, for teacher view)
	QuestionCount int      `json:"question_count,omitempty"`
	AttemptCount  int      `json:"attempt_count,omitempty"`
	StudentCount  int      `json:"student_count,omitempty"`
	AverageScore  *float64 `json:"average_score,omitempty"`
}

// ============================================
// QUESTION DTOs
// ============================================

// QuestionType represents the type of question
type QuestionType string

const (
	QuestionTypeSingleChoice      QuestionType = "SINGLE_CHOICE"
	QuestionTypeMultipleChoice    QuestionType = "MULTIPLE_CHOICE"
	QuestionTypeShortAnswer       QuestionType = "SHORT_ANSWER"
	QuestionTypeEssay             QuestionType = "ESSAY"
	QuestionTypeFileUpload        QuestionType = "FILE_UPLOAD"
	QuestionTypeFillBlankText     QuestionType = "FILL_BLANK_TEXT"
	QuestionTypeFillBlankDropdown QuestionType = "FILL_BLANK_DROPDOWN"
)

// CreateQuestionRequest represents request to create a question
type CreateQuestionRequest struct {
	QuizID         int64                  `json:"quiz_id" binding:"required"`
	QuestionType   QuestionType           `json:"question_type" binding:"required"`
	QuestionText   string                 `json:"question_text" binding:"required"`
	QuestionHTML   string                 `json:"question_html"`
	Explanation    string                 `json:"explanation"`
	Points         float64                `json:"points" binding:"required,min=0"`
	OrderIndex     int                    `json:"order_index" binding:"required,min=0"`
	Settings       map[string]interface{} `json:"settings"`
	IsRequired     bool                   `json:"is_required"`
	
	// Answer options (for choice questions)
	AnswerOptions  []CreateAnswerOptionRequest  `json:"answer_options"`
	
	// Correct answers (for text/fill-blank questions)
	CorrectAnswers []CreateCorrectAnswerRequest `json:"correct_answers"`
}

// UpdateQuestionRequest represents request to update a question
type UpdateQuestionRequest struct {
	QuestionText   *string                 `json:"question_text"`
	QuestionHTML   *string                 `json:"question_html"`
	Explanation    *string                 `json:"explanation"`
	Points         *float64                `json:"points"`
	OrderIndex     *int                    `json:"order_index"`
	Settings       *map[string]interface{} `json:"settings"`
	IsRequired     *bool                   `json:"is_required"`
}

// QuestionResponse represents question details
type QuestionResponse struct {
	ID             int64                   `json:"id"`
	QuizID         int64                   `json:"quiz_id"`
	QuestionType   QuestionType            `json:"question_type"`
	QuestionText   string                  `json:"question_text"`
	QuestionHTML   string                  `json:"question_html,omitempty"`
	Explanation    string                  `json:"explanation,omitempty"`
	Points         float64                 `json:"points"`
	OrderIndex     int                     `json:"order_index"`
	Settings       map[string]interface{}  `json:"settings,omitempty"`
	Images         []QuestionImage         `json:"images,omitempty"` // Extracted from settings
	IsRequired     bool                    `json:"is_required"`
	CreatedAt      time.Time               `json:"created_at"`
	UpdatedAt      time.Time               `json:"updated_at"`
	
	// Related data
	AnswerOptions  []AnswerOptionResponse  `json:"answer_options,omitempty"`
	CorrectAnswers []CorrectAnswerResponse `json:"correct_answers,omitempty"`
}

// StudentQuestionResponse - question view for students (hides correct answers)
type StudentQuestionResponse struct {
	ID             int64                          `json:"id"`
	QuizID         int64                          `json:"quiz_id"`
	QuestionType   QuestionType                   `json:"question_type"`
	QuestionText   string                         `json:"question_text"`
	QuestionHTML   string                         `json:"question_html,omitempty"`
	Points         float64                        `json:"points"`
	OrderIndex     int                            `json:"order_index"`
	Settings       map[string]interface{}         `json:"settings,omitempty"`
	Images         []QuestionImage                `json:"images,omitempty"` // Students can see images
	IsRequired     bool                           `json:"is_required"`
	
	// Answer options without correct flag
	AnswerOptions  []StudentAnswerOptionResponse  `json:"answer_options,omitempty"`
}

// ============================================
// ANSWER OPTION DTOs
// ============================================

// CreateAnswerOptionRequest represents request to create answer option
type CreateAnswerOptionRequest struct {
	OptionText string `json:"option_text" binding:"required"`
	OptionHTML string `json:"option_html"`
	IsCorrect  bool   `json:"is_correct"`
	OrderIndex int    `json:"order_index" binding:"required,min=0"`
	BlankID    *int   `json:"blank_id"` // For fill-in-the-blank dropdown
}

// AnswerOptionResponse represents answer option
type AnswerOptionResponse struct {
	ID         int64              `json:"id"`
	QuestionID int64              `json:"question_id"`
	OptionText string             `json:"option_text"`
	OptionHTML string             `json:"option_html,omitempty"`
	IsCorrect  bool               `json:"is_correct"`
	OrderIndex int                `json:"order_index"`
	BlankID    *int               `json:"blank_id,omitempty"`
	Image      *AnswerOptionImage `json:"image,omitempty"`
	CreatedAt  time.Time          `json:"created_at"`
}

// StudentAnswerOptionResponse - answer option for students (hides is_correct)
type StudentAnswerOptionResponse struct {
	ID         int64              `json:"id"`
	QuestionID int64              `json:"question_id"`
	OptionText string             `json:"option_text"`
	OptionHTML string             `json:"option_html,omitempty"`
	OrderIndex int                `json:"order_index"`
	BlankID    *int               `json:"blank_id,omitempty"`
	Image      *AnswerOptionImage `json:"image,omitempty"`
}

// ============================================
// CORRECT ANSWER DTOs
// ============================================

// CreateCorrectAnswerRequest represents correct answer
type CreateCorrectAnswerRequest struct {
	AnswerText    string `json:"answer_text"`
	BlankID       *int   `json:"blank_id"`
	BlankPosition *int   `json:"blank_position"`
	CaseSensitive bool   `json:"case_sensitive"`
	ExactMatch    bool   `json:"exact_match"`
}

// CorrectAnswerResponse represents correct answer
type CorrectAnswerResponse struct {
	ID            int64     `json:"id"`
	QuestionID    int64     `json:"question_id"`
	AnswerText    string    `json:"answer_text,omitempty"`
	BlankID       *int      `json:"blank_id,omitempty"`
	BlankPosition *int      `json:"blank_position,omitempty"`
	CaseSensitive bool      `json:"case_sensitive"`
	ExactMatch    bool      `json:"exact_match"`
	CreatedAt     time.Time `json:"created_at"`
}

// ============================================
// QUIZ ATTEMPT DTOs
// ============================================

// StartQuizAttemptRequest represents request to start quiz
type StartQuizAttemptRequest struct {
	QuizID int64 `json:"quiz_id" binding:"required"`
}

// QuizAttemptResponse represents quiz attempt
type QuizAttemptResponse struct {
	ID               int64      `json:"id"`
	QuizID           int64      `json:"quiz_id"`
	StudentID        int64      `json:"student_id"`
	AttemptNumber    int        `json:"attempt_number"`
	StartedAt        time.Time  `json:"started_at"`
	SubmittedAt      *time.Time `json:"submitted_at,omitempty"`
	TimeSpentSeconds *int       `json:"time_spent_seconds,omitempty"`
	TotalPoints      *float64   `json:"total_points,omitempty"`
	EarnedPoints     *float64   `json:"earned_points,omitempty"`
	Percentage       *float64   `json:"percentage,omitempty"`
	IsPassed         *bool      `json:"is_passed,omitempty"`
	Status           string     `json:"status"`
	CreatedAt        time.Time  `json:"created_at"`
	UpdatedAt        time.Time  `json:"updated_at"`
}

// SubmitAnswerRequest represents submitting an answer
type SubmitAnswerRequest struct {
	AttemptID  int64                  `json:"attempt_id" binding:"required"`
	QuestionID int64                  `json:"question_id" binding:"required"`
	AnswerData map[string]interface{} `json:"answer_data" binding:"required"`
}

// StudentAnswerResponse represents student's answer
type StudentAnswerResponse struct {
	ID               int64                  `json:"id"`
	AttemptID        int64                  `json:"attempt_id"`
	QuestionID       int64                  `json:"question_id"`
	AnswerData       map[string]interface{} `json:"answer_data"`
	PointsEarned     *float64               `json:"points_earned,omitempty"`
	IsCorrect        *bool                  `json:"is_correct,omitempty"`
	GraderFeedback   string                 `json:"grader_feedback,omitempty"`
	GradedBy         *int64                 `json:"graded_by,omitempty"`
	GradedAt         *time.Time             `json:"graded_at,omitempty"`
	AnsweredAt       time.Time              `json:"answered_at"`
	TimeSpentSeconds *int                   `json:"time_spent_seconds,omitempty"`
}

// SubmitQuizRequest represents submitting entire quiz
type SubmitQuizRequest struct {
	AttemptID int64 `json:"attempt_id" binding:"required"`
}

// QuizResultResponse represents quiz results after submission
type QuizResultResponse struct {
	Attempt            QuizAttemptResponse     `json:"attempt"`
	Quiz               QuizResponse            `json:"quiz"`
	Questions          []QuestionResponse      `json:"questions,omitempty"`
	StudentAnswers     []StudentAnswerResponse `json:"student_answers"`
	ShowCorrectAnswers bool                    `json:"show_correct_answers"`
	AllowReview        bool                    `json:"allow_review"`
}

// ============================================
// GRADING DTOs
// ============================================

// GradeAnswerRequest represents manual grading
type GradeAnswerRequest struct {
	AnswerID       int64   `json:"answer_id" binding:"required"`
	PointsEarned   float64 `json:"points_earned" binding:"required,min=0"`
	GraderFeedback string  `json:"grader_feedback"`
}

// BulkGradeRequest represents bulk grading
type BulkGradeRequest struct {
	Grades []GradeAnswerRequest `json:"grades" binding:"required,min=1"`
}

// StudentAnswerForGrading represents an answer that needs grading
type StudentAnswerForGrading struct {
	ID             int64                  `json:"id"`
	AttemptID      int64                  `json:"attempt_id"`
	StudentID      int64                  `json:"student_id"`
	StudentName    string                 `json:"student_name"`
	StudentEmail   string                 `json:"student_email"`
	QuestionID     int64                  `json:"question_id"`
	QuestionText   string                 `json:"question_text"`
	QuestionType   string                 `json:"question_type"`
	QuestionImages []QuestionImage        `json:"question_images,omitempty"`
	Points         float64                `json:"points"`
	AnswerData     map[string]interface{} `json:"answer_data"`
	PointsEarned   *float64               `json:"points_earned,omitempty"`
	Feedback       string                 `json:"feedback,omitempty"`
	AnsweredAt     time.Time              `json:"answered_at"`
}

// ============================================
// ANALYTICS DTOs
// ============================================

// QuizAnalyticsResponse represents quiz analytics
type QuizAnalyticsResponse struct {
	QuizID            int64                        `json:"quiz_id"`
	QuizTitle         string                       `json:"quiz_title"`
	TotalAttempts     int                          `json:"total_attempts"`
	UniqueStudents    int                          `json:"unique_students"`
	AverageScore      float64                      `json:"average_score"`
	PassRate          float64                      `json:"pass_rate"`
	QuestionAnalytics []QuestionAnalyticsResponse  `json:"question_analytics"`
}

// QuestionAnalyticsResponse represents question analytics
type QuestionAnalyticsResponse struct {
	QuestionID       int64   `json:"question_id"`
	QuestionText     string  `json:"question_text"`
	QuestionType     string  `json:"question_type"`
	TotalAttempts    int     `json:"total_attempts"`
	CorrectCount     int     `json:"correct_count"`
	IncorrectCount   int     `json:"incorrect_count"`
	AverageScore     float64 `json:"average_score"`
	DifficultyRating string  `json:"difficulty_rating"`
}

// ============================================
// REVIEW DTOs
// ============================================

// QuizReviewRequest represents request to review quiz
type QuizReviewRequest struct {
	AttemptID int64 `json:"attempt_id" binding:"required"`
}

// QuizReviewResponse represents quiz review (for students)
type QuizReviewResponse struct {
	Attempt              QuizAttemptResponse          `json:"attempt"`
	Quiz                 QuizResponse                 `json:"quiz"`
	QuestionsWithAnswers []QuestionWithAnswerResponse `json:"questions_with_answers"`
	ShowCorrectAnswers   bool                         `json:"show_correct_answers"`
	ShowFeedback         bool                         `json:"show_feedback"`
}

// QuestionWithAnswerResponse combines question and student answer
type QuestionWithAnswerResponse struct {
	Question      QuestionResponse       `json:"question"`
	StudentAnswer *StudentAnswerResponse `json:"student_answer,omitempty"`
}

// ============================================
// LIST/FILTER DTOs
// ============================================

// ListQuizzesRequest represents filtering options
type ListQuizzesRequest struct {
	CourseID    *int64 `form:"course_id"`
	SectionID   *int64 `form:"section_id"`
	IsPublished *bool  `form:"is_published"`
	PaginationRequest
}

// ListAttemptsRequest represents filtering for attempts
type ListAttemptsRequest struct {
	QuizID    *int64  `form:"quiz_id"`
	StudentID *int64  `form:"student_id"`
	Status    *string `form:"status"`
	PaginationRequest
}