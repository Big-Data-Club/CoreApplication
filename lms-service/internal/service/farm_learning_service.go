package service

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"strings"

	"example/hello/internal/repository"
)

type FarmQuestion struct {
	ID          string   `json:"id"`
	Kind        string   `json:"kind"`
	Prompt      string   `json:"prompt"`
	Options     []string `json:"options,omitempty"`
	Answer      string   `json:"answer"`
	Explanation string   `json:"explanation,omitempty"`
	CourseID    int64    `json:"course_id"`
	NodeID      *int64   `json:"node_id,omitempty"`
}

type FarmAttempt struct {
	ChallengeID string `json:"challenge_id"`
	UserID      int64  `json:"user_id"`
	CourseID    int64  `json:"course_id"`
	NodeID      *int64 `json:"node_id,omitempty"`
	SourceID    string `json:"source_id"`
	Kind        string `json:"kind"`
	Correct     bool   `json:"correct"`
}

type FarmLearningService struct {
	db         *sql.DB
	flashcards *FlashcardService
	mastery    *repository.MicroInteractionRepository
}

func NewFarmLearningService(db *sql.DB, cards *FlashcardService, mastery *repository.MicroInteractionRepository) *FarmLearningService {
	return &FarmLearningService{db: db, flashcards: cards, mastery: mastery}
}

func randomIndex(length int) int {
	n, err := rand.Int(rand.Reader, big.NewInt(int64(length)))
	if err != nil {
		return 0
	}
	return int(n.Int64())
}

func pickFarmQuestion(choices []*FarmQuestion, exclude string) *FarmQuestion {
	if len(choices) > 1 && exclude != "" {
		other := make([]*FarmQuestion, 0, len(choices))
		for _, q := range choices {
			if q.ID != exclude {
				other = append(other, q)
			}
		}
		if len(other) > 0 {
			choices = other
		}
	}
	return choices[randomIndex(len(choices))]
}

func (s *FarmLearningService) Question(ctx context.Context, userID int64, kind, exclude string) (*FarmQuestion, error) {
	if userID <= 0 || (kind != "quiz" && kind != "flashcard") {
		return nil, fmt.Errorf("invalid farm question request")
	}
	if kind == "quiz" {
		return s.quizQuestion(ctx, userID, exclude)
	}
	return s.flashcardQuestion(ctx, userID, exclude)
}

func (s *FarmLearningService) quizQuestion(ctx context.Context, userID int64, exclude string) (*FarmQuestion, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT q.id, q.course_id, q.node_id, q.question_text, q.explanation, q.answer_options
		FROM question_bank_items q
		JOIN enrollments e ON e.course_id=q.course_id AND e.student_id=$1 AND e.status='ACCEPTED'
		JOIN courses c ON c.id=q.course_id AND c.status='PUBLISHED'
		WHERE q.status='APPROVED' AND q.question_type='SINGLE_CHOICE'
		  AND jsonb_array_length(q.answer_options) BETWEEN 2 AND 8
		ORDER BY q.id DESC LIMIT 100`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	type option struct {
		OptionText string `json:"option_text"`
		IsCorrect  bool   `json:"is_correct"`
		OrderIndex int    `json:"order_index"`
	}
	var choices []*FarmQuestion
	for rows.Next() {
		var id, courseID int64
		var node sql.NullInt64
		var prompt string
		var explanation sql.NullString
		var raw []byte
		if err = rows.Scan(&id, &courseID, &node, &prompt, &explanation, &raw); err != nil {
			return nil, err
		}
		var options []option
		if json.Unmarshal(raw, &options) != nil || len(options) < 2 {
			continue
		}
		// The stored order index is part of the LMS answer contract.
		for i := 0; i < len(options); i++ {
			for j := i + 1; j < len(options); j++ {
				if options[j].OrderIndex < options[i].OrderIndex {
					options[i], options[j] = options[j], options[i]
				}
			}
		}
		q := &FarmQuestion{ID: fmt.Sprintf("lms:quiz:%d", id), Kind: "quiz", Prompt: prompt, Explanation: explanation.String, CourseID: courseID}
		if node.Valid {
			v := node.Int64
			q.NodeID = &v
		}
		correct := -1
		for i, item := range options {
			q.Options = append(q.Options, item.OptionText)
			if item.IsCorrect {
				if correct >= 0 {
					correct = -2
					break
				}
				correct = i
			}
		}
		if correct < 0 || strings.TrimSpace(prompt) == "" {
			continue
		}
		q.Answer = fmt.Sprint(correct)
		choices = append(choices, q)
	}
	if err = rows.Err(); err != nil {
		return nil, err
	}
	if len(choices) == 0 {
		return nil, sql.ErrNoRows
	}
	return pickFarmQuestion(choices, exclude), nil
}

func (s *FarmLearningService) flashcardQuestion(ctx context.Context, userID int64, exclude string) (*FarmQuestion, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT e.course_id FROM enrollments e JOIN courses c ON c.id=e.course_id
		WHERE e.student_id=$1 AND e.status='ACCEPTED' AND c.status='PUBLISHED' ORDER BY e.enrolled_at DESC LIMIT 5`, userID)
	if err != nil {
		return nil, err
	}
	var courses []int64
	for rows.Next() {
		var id int64
		if err = rows.Scan(&id); err != nil {
			rows.Close()
			return nil, err
		}
		courses = append(courses, id)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	for _, courseID := range courses {
		cards, e := s.flashcards.ListDueFlashcards(ctx, userID, courseID)
		if e == nil && len(cards) == 0 {
			cards, e = s.flashcards.ListFlashcards(ctx, userID, courseID, nil, nil, nil)
		}
		if e != nil {
			return nil, e
		}
		var choices []*FarmQuestion
		for _, card := range cards {
			id := fmt.Sprintf("lms:flashcard:%d", card.ID)
			if card.Status != "ACTIVE" || strings.TrimSpace(card.FrontText) == "" || strings.TrimSpace(card.BackText) == "" || len([]rune(card.BackText)) > 160 {
				continue
			}
			choices = append(choices, &FarmQuestion{ID: id, Kind: "flashcard", Prompt: card.FrontText, Answer: card.BackText, Explanation: card.BackText, CourseID: courseID, NodeID: card.NodeID})
		}
		if len(choices) > 0 {
			return pickFarmQuestion(choices, exclude), nil
		}
	}
	return nil, sql.ErrNoRows
}

// RecordAttempt is idempotent and updates the raw interaction and heatmap in
// one LMS transaction. Farm delivers this through its durable outbox.
func (s *FarmLearningService) RecordAttempt(ctx context.Context, a FarmAttempt) error {
	if a.UserID <= 0 || a.CourseID <= 0 || a.ChallengeID == "" || a.SourceID == "" || (a.Kind != "quiz" && a.Kind != "flashcard") {
		return fmt.Errorf("invalid farm attempt")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var inserted string
	err = tx.QueryRowContext(ctx, `INSERT INTO farm_learning_attempts(challenge_id,user_id,course_id,node_id,source_id,kind,correct)
		VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(challenge_id) DO NOTHING RETURNING challenge_id::text`, a.ChallengeID, a.UserID, a.CourseID, a.NodeID, a.SourceID, a.Kind, a.Correct).Scan(&inserted)
	if errors.Is(err, sql.ErrNoRows) {
		var userID, courseID int64
		var sourceID, kind string
		var correct bool
		if err = tx.QueryRowContext(ctx, `SELECT user_id,course_id,source_id,kind,correct FROM farm_learning_attempts WHERE challenge_id=$1`, a.ChallengeID).Scan(&userID, &courseID, &sourceID, &kind, &correct); err != nil {
			return err
		}
		if userID != a.UserID || courseID != a.CourseID || sourceID != a.SourceID || kind != a.Kind || correct != a.Correct {
			return fmt.Errorf("conflicting farm attempt replay")
		}
		return tx.Commit()
	}
	if err != nil {
		return err
	}
	action := "quick_check_attempt"
	if a.Kind == "flashcard" {
		action = "flashcard_rate"
	}
	score := 0.0
	if a.Correct {
		score = 1
	}
	payload, _ := json.Marshal(map[string]interface{}{"source": "knowledge_farm", "challenge_id": a.ChallengeID, "source_id": a.SourceID})
	_, err = tx.ExecContext(ctx, `INSERT INTO micro_lesson_interactions(user_id,course_id,node_id,action_type,score,status,payload)
		VALUES($1,$2,$3,$4,$5,$6,$7)`, a.UserID, a.CourseID, a.NodeID, action, score, map[bool]string{true: "correct", false: "incorrect"}[a.Correct], payload)
	if err != nil {
		return err
	}
	if a.NodeID != nil {
		delta := repository.MasteryComponentDelta{UserID: a.UserID, CourseID: a.CourseID, NodeID: *a.NodeID}
		if a.Kind == "quiz" {
			delta.MiniQuizSample = &score
		} else {
			engaged := 1.0 // Same meaning as LMS flashcard_rate events.
			delta.EngagementSample = &engaged
		}
		if err = s.mastery.ApplyDeltaTx(ctx, tx, delta); err != nil {
			return err
		}
	}
	return tx.Commit()
}
