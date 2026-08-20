package dto

import "time"

// ══════════════════════════════════════════════════════════════════════════════
// LEARNING EVENT DTOs
// ══════════════════════════════════════════════════════════════════════════════

// TrackLearningEventRequest represents a learning event from the frontend
type TrackLearningEventRequest struct {
	EventType      string                 `json:"event_type" binding:"required,oneof=lesson_opened lesson_started lesson_completed lesson_abandoned lesson_resumed question_viewed answer_submitted answer_retried hint_requested recommendation_clicked"`
	SessionID      string                 `json:"session_id" binding:"max=100"`
	CourseID       *int64                 `json:"course_id"`
	LessonID       *int64                 `json:"lesson_id"`
	QuestionID     *int64                 `json:"question_id"`
	SkillID        *int64                 `json:"skill_id"`
	Difficulty     *float64               `json:"difficulty" binding:"omitempty,min=0,max=1"`
	Correct        *bool                  `json:"correct"`
	AttemptNo      *int                   `json:"attempt_no" binding:"omitempty,min=1"`
	ResponseTimeMs *int64                 `json:"response_time_ms" binding:"omitempty,min=0"`
	HintCount      *int                   `json:"hint_count" binding:"omitempty,min=0"`
	Metadata       map[string]interface{} `json:"metadata"`
}

// LearningEventResponse represents a tracked learning event
type LearningEventResponse struct {
	ID             int64                  `json:"id"`
	EventID        string                 `json:"event_id"`
	EventType      string                 `json:"event_type"`
	StudentID      int64                  `json:"student_id"`
	SessionID      string                 `json:"session_id,omitempty"`
	CourseID       *int64                 `json:"course_id,omitempty"`
	LessonID       *int64                 `json:"lesson_id,omitempty"`
	QuestionID     *int64                 `json:"question_id,omitempty"`
	SkillID        *int64                 `json:"skill_id,omitempty"`
	Difficulty     *float64               `json:"difficulty,omitempty"`
	Correct        *bool                  `json:"correct,omitempty"`
	AttemptNo      *int                   `json:"attempt_no,omitempty"`
	ResponseTimeMs *int64                 `json:"response_time_ms,omitempty"`
	HintCount      *int                   `json:"hint_count,omitempty"`
	Metadata       map[string]interface{} `json:"metadata,omitempty"`
	CreatedAt      time.Time              `json:"created_at"`
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILL DTOs
// ══════════════════════════════════════════════════════════════════════════════

// CreateSkillRequest represents a request to create a skill
type CreateSkillRequest struct {
	Name          string   `json:"name" binding:"required,min=3,max=255"`
	Description   string   `json:"description" binding:"max=1000"`
	ParentSkillID *int64   `json:"parent_skill_id"`
	Difficulty    *float64 `json:"difficulty" binding:"omitempty,min=0,max=1"`
}

// UpdateSkillRequest represents a request to update a skill
type UpdateSkillRequest struct {
	Name          *string  `json:"name" binding:"omitempty,min=3,max=255"`
	Description   *string  `json:"description" binding:"omitempty,max=1000"`
	ParentSkillID *int64   `json:"parent_skill_id"`
	Difficulty    *float64 `json:"difficulty" binding:"omitempty,min=0,max=1"`
}

// SkillResponse represents a skill
type SkillResponse struct {
	ID            int64     `json:"id"`
	Name          string    `json:"name"`
	Description   string    `json:"description,omitempty"`
	ParentSkillID *int64    `json:"parent_skill_id,omitempty"`
	Difficulty    *float64  `json:"difficulty,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// AddPrerequisiteRequest represents a request to add a skill prerequisite
type AddPrerequisiteRequest struct {
	PrerequisiteSkillID int64    `json:"prerequisite_skill_id" binding:"required"`
	Strength            *float64 `json:"strength" binding:"omitempty,min=0,max=1"`
}

// SkillPrerequisiteResponse represents a skill prerequisite
type SkillPrerequisiteResponse struct {
	ID                  int64     `json:"id"`
	SkillID             int64     `json:"skill_id"`
	PrerequisiteSkillID int64     `json:"prerequisite_skill_id"`
	Strength            float64   `json:"strength"`
	CreatedAt           time.Time `json:"created_at"`
}

// MapSkillRequest represents a request to map content/question to skill
type MapSkillRequest struct {
	SkillID    int64    `json:"skill_id" binding:"required"`
	Difficulty *float64 `json:"difficulty" binding:"omitempty,min=0,max=1"`
	Weight     *float64 `json:"weight" binding:"omitempty,min=0,max=1"`
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNER SKILL STATE DTOs (For Student View)
// ══════════════════════════════════════════════════════════════════════════════

// LearnerSkillStateResponse represents a student's mastery of a skill
type LearnerSkillStateResponse struct {
	SkillID               int64      `json:"skill_id"`
	SkillName             string     `json:"skill_name"`
	SkillDescription      string     `json:"skill_description,omitempty"`
	MasteryScore          float64    `json:"mastery_score"`           // 0-1
	MasteryLevel          string     `json:"mastery_level"`           // struggling, developing, advancing, mastered
	MasteryPercentage     int        `json:"mastery_percentage"`      // 0-100 for UI display
	ConfidenceScore       float64    `json:"confidence_score"`        // 0-1
	AttemptCount          int        `json:"attempt_count"`
	Accuracy              float64    `json:"accuracy"`                // 0-1
	AvgResponseTimeMs     *int64     `json:"avg_response_time_ms,omitempty"`
	HintDependency        float64    `json:"hint_dependency"`         // 0-1
	RecommendedDifficulty *float64   `json:"recommended_difficulty,omitempty"`
	LastPracticedAt       *time.Time `json:"last_practiced_at,omitempty"`
	UpdatedAt             time.Time  `json:"updated_at"`

	// UI-friendly fields
	NeedsReview           bool       `json:"needs_review"`            // For spaced repetition
	IsStruggling          bool       `json:"is_struggling"`
	ProgressIndicator     string     `json:"progress_indicator"`      // "🔴", "🟡", "🟢", "⭐"
	NextAction            string     `json:"next_action"`             // "review", "practice", "advance"
}

// StudentSkillsOverviewResponse represents all skills for a student
type StudentSkillsOverviewResponse struct {
	StudentID          int64                        `json:"student_id"`
	CourseID           *int64                       `json:"course_id,omitempty"`
	TotalSkills        int                          `json:"total_skills"`
	MasteredSkills     int                          `json:"mastered_skills"`
	StrugglingSkills   int                          `json:"struggling_skills"`
	OverallProgress    int                          `json:"overall_progress"`    // 0-100
	Skills             []LearnerSkillStateResponse  `json:"skills"`
	RecommendedActions []RecommendedAction          `json:"recommended_actions"` // Top 3 actions
}

// RecommendedAction represents what student should do next
type RecommendedAction struct {
	Action      string  `json:"action"`       // "review", "practice", "advance", "learn_new"
	SkillID     int64   `json:"skill_id"`
	SkillName   string  `json:"skill_name"`
	Reason      string  `json:"reason"`       // User-friendly reason in Vietnamese
	Priority    int     `json:"priority"`     // 1 = highest
	Icon        string  `json:"icon"`         // Emoji or icon name
	ActionText  string  `json:"action_text"`  // "Củng cố", "Luyện tập", "Thử thách"
}

// ══════════════════════════════════════════════════════════════════════════════
// PERSONALIZED RECOMMENDATIONS DTOs
// ══════════════════════════════════════════════════════════════════════════════

// PersonalizedRecommendationResponse represents a personalized content recommendation
type PersonalizedRecommendationResponse struct {
	ContentID         int64    `json:"content_id"`
	ContentTitle      string   `json:"content_title"`
	ContentType       string   `json:"content_type"`         // "lesson", "quiz", "practice"
	SkillID           int64    `json:"skill_id"`
	SkillName         string   `json:"skill_name"`
	Difficulty        float64  `json:"difficulty"`
	CurrentMastery    float64  `json:"current_mastery"`      // Student's current mastery 0-1
	TargetMastery     float64  `json:"target_mastery"`       // Expected mastery after 0-1
	Reason            string   `json:"reason"`               // Vietnamese explanation
	ReasonType        string   `json:"reason_type"`          // "struggling", "practice", "advance", "new"
	EstimatedMinutes  int      `json:"estimated_minutes"`
	Priority          int      `json:"priority"`             // 1 = highest
	Badge             string   `json:"badge,omitempty"`      // "Cần ôn tập", "Thử thách mới"
	Icon              string   `json:"icon"`                 // Emoji
	ActionButton      string   `json:"action_button"`        // "Bắt đầu ôn tập", "Tiếp tục học"
	ImpactDescription string   `json:"impact_description"`   // What they'll achieve
}

// DailyRecommendationsResponse represents today's recommended learning
type DailyRecommendationsResponse struct {
	StudentID               int64                                 `json:"student_id"`
	GeneratedAt             time.Time                             `json:"generated_at"`
	Greeting                string                                `json:"greeting"`                  // "Chào buổi sáng!", personalized
	MotivationalMessage     string                                `json:"motivational_message"`      // Encouraging message
	PriorityRecommendations []PersonalizedRecommendationResponse  `json:"priority_recommendations"`  // Top 3-5
	OptionalRecommendations []PersonalizedRecommendationResponse  `json:"optional_recommendations"`  // If time allows
	SkillsNeedingReview     []LearnerSkillStateResponse           `json:"skills_needing_review"`     // Spaced repetition
	LearningStreak          int                                   `json:"learning_streak"`           // Days in a row
	TodayGoal               string                                `json:"today_goal"`                // "Hoàn thành 2 bài học"
}

// DiscoverCoursesRecommendationResponse for course discovery page
type DiscoverCoursesRecommendationResponse struct {
	Courses              []RecommendedCourseItem `json:"courses"`
	RecommendationReason string                  `json:"recommendation_reason"`
	PersonalizationLevel string                  `json:"personalization_level"` // "high", "medium", "low"
}

// RecommendedCourseItem represents a course recommendation
type RecommendedCourseItem struct {
	CourseID            int64    `json:"course_id"`
	Title               string   `json:"title"`
	Description         string   `json:"description"`
	Category            string   `json:"category"`
	Level               string   `json:"level"`
	ThumbnailURL        string   `json:"thumbnail_url,omitempty"`
	EnrollmentCount     int      `json:"enrollment_count"`
	MatchScore          float64  `json:"match_score"`          // 0-1, how well it matches
	MatchReason         string   `json:"match_reason"`         // Why recommended
	SkillsYouWillLearn  []string `json:"skills_you_will_learn"` // Top 3-5 skills
	RelevantSkills      []string `json:"relevant_skills"`       // Skills student already has
	Badge               string   `json:"badge,omitempty"`       // "Phù hợp với bạn", "Xu hướng"
	EstimatedDuration   string   `json:"estimated_duration"`    // "4 tuần", "20 giờ"
	DifficultyMatch     string   `json:"difficulty_match"`      // "perfect", "good", "challenging"
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNING TRAJECTORY DTOs
// ══════════════════════════════════════════════════════════════════════════════

// StudentLearningTrajectoryResponse shows complete learning history
type StudentLearningTrajectoryResponse struct {
	StudentID     int64                   `json:"student_id"`
	TotalEvents   int                     `json:"total_events"`
	DateRange     string                  `json:"date_range"`
	Events        []LearningEventResponse `json:"events"`
	TimelineView  []TimelineEvent         `json:"timeline_view"`  // Grouped by day
}

// TimelineEvent represents events grouped by date
type TimelineEvent struct {
	Date        string                  `json:"date"`          // "2026-08-20"
	EventCount  int                     `json:"event_count"`
	Summary     string                  `json:"summary"`       // "Hoàn thành 3 bài, trả lời 15 câu hỏi"
	Events      []LearningEventResponse `json:"events"`
	Achievements []string                `json:"achievements"`  // ["Mastered Basic Algebra", "3-day streak"]
}
