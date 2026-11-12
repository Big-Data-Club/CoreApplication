package dto

// QuizResultsQuery bounds the visible rows without changing whole-quiz metrics.
type QuizResultsQuery struct {
	AttemptPage int
	StudentPage int
	Search      string
}
