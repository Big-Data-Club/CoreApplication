package repository

// Mastery weight scheme. Sums to 1.0. Tweaking the weights here is the
// single source of truth — the SQL `UPDATE ... SET mastery_level = ...`
// recompute reads them from these constants.
const (
	WeightFormalQuiz = 0.60 // Bloom's-taxonomy formal quizzes
	WeightMiniQuiz   = 0.20 // Quick Action Panel concept checks
	WeightCompletion = 0.10 // Micro-lesson completion
	WeightEngagement = 0.10 // Flashcard / Ask-AI engagement
)

// MasteryStatusLabel maps a 0.0–1.0 mastery score to a human-readable
// status used by the heatmap UI.
func MasteryStatusLabel(level float64) string {
	switch {
	case level >= 0.8:
		return "Rất tốt"
	case level >= 0.6:
		return "TB"
	case level >= 0.4:
		return "Yếu"
	default:
		return "Cần cải thiện"
	}
}
