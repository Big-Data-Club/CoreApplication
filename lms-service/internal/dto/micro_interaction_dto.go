package dto

import "time"

// MicroInteractionRequest is the body of POST /analytics/micro-interaction.
// Triggered by the Quick Action Panel on the MicroLessonViewer.
type MicroInteractionRequest struct {
	CourseID   int64                  `json:"course_id" binding:"required"`
	LessonID   *int64                 `json:"lesson_id"`
	NodeID     *int64                 `json:"node_id"`
	ActionType string                 `json:"action_type" binding:"required"`
	Score      *float64               `json:"score"`
	Status     string                 `json:"status"`
	Payload    map[string]interface{} `json:"payload"`
}

// MicroInteractionResponse is returned 202-Accepted from the endpoint.
type MicroInteractionResponse struct {
	InteractionID int64     `json:"interaction_id"`
	AcceptedAt    time.Time `json:"accepted_at"`
}

// ── Heatmap ─────────────────────────────────────────────────────────

// HeatmapNodeMastery is a single row of the composite heatmap
// returned by GET /analytics/heatmap. The mastery_level field is the
// 0.0–1.0 weighted score; component fields expose the breakdown so
// the dashboard can render contribution bars.
type HeatmapNodeMastery struct {
	NodeID            int64     `json:"node_id"`
	UserCount         int       `json:"user_count"`
	MasteryLevel      float64   `json:"mastery_level"`
	FormalQuizScore   float64   `json:"formal_quiz_score"`
	MiniQuizScore     float64   `json:"mini_quiz_score"`
	CompletionScore   float64   `json:"completion_score"`
	EngagementScore   float64   `json:"engagement_score"`
	StatusLevel       string    `json:"status_level"`
	LastInteractionAt time.Time `json:"last_interaction_at"`
}

// HeatmapResponse wraps the heatmap rows with the weight scheme that
// produced them - the FE renders the legend off this.
type HeatmapResponse struct {
	CourseID int64                `json:"course_id"`
	Weights  HeatmapWeights       `json:"weights"`
	Nodes    []HeatmapNodeMastery `json:"nodes"`
}

type HeatmapWeights struct {
	FormalQuiz float64 `json:"formal_quiz"`
	MiniQuiz   float64 `json:"mini_quiz"`
	Completion float64 `json:"completion"`
	Engagement float64 `json:"engagement"`
}
