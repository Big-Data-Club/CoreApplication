package service

import (
	"context"
	"encoding/json"
	"fmt"
)

type QuizIndexRequest struct {
	Force       bool   `json:"force"`
	Query       string `json:"query"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Offset      int    `json:"offset"`
	QuestionID  int64  `json:"question_id"`
	NodeID      int64  `json:"node_id"`
	SourceHash  string `json:"source_hash"`
}

func (s *QuizService) QuizIndexSource(ctx context.Context, quizID, userID, after int64, head bool) (interface{}, error) {
	// Internal workers delegate to a real, currently authorized LMS identity.
	roles, err := s.userRepo.GetUserRoles(ctx, userID)
	if err != nil {
		return nil, err
	}
	role := "TEACHER"
	for _, r := range roles {
		if r == "ADMIN" {
			role = "ADMIN"
		}
	}
	if err = s.AuthorizeQuizResults(ctx, quizID, userID, role); err != nil {
		return nil, err
	}
	courseID, err := s.quizRepo.GetQuizCourseID(ctx, quizID)
	if err != nil || courseID <= 0 {
		return nil, fmt.Errorf("quiz course not found")
	}
	raw, err := s.quizRepo.QuizIndexSource(ctx, quizID, after, head)
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{"quiz_id": quizID, "course_id": courseID, "data": raw}, nil
}

func (s *QuizService) QuizIndexAction(ctx context.Context, quizID, userID int64, role, action string, request QuizIndexRequest) (json.RawMessage, error) {
	if err := s.AuthorizeQuizResults(ctx, quizID, userID, role); err != nil {
		return nil, err
	}
	courseID, err := s.quizRepo.GetQuizCourseID(ctx, quizID)
	if err != nil || courseID <= 0 {
		return nil, fmt.Errorf("quiz course not found")
	}
	head, err := s.quizRepo.QuizIndexSource(ctx, quizID, 0, true)
	if err != nil {
		return nil, err
	}
	var metadata map[string]interface{}
	if err = json.Unmarshal(head, &metadata); err != nil {
		return nil, err
	}
	body := map[string]interface{}{"quiz_id": quizID, "course_id": courseID, "requester_id": userID,
		"force": request.Force,
		"name":  request.Name, "description": request.Description, "offset": request.Offset, "revision": metadata["revision"], "total": metadata["total"], "query": request.Query,
		"question_id": request.QuestionID, "node_id": request.NodeID, "source_hash": request.SourceHash}
	remote := action
	if action == "link" {
		remote = "node"
	}
	result, err := s.aiClient.QuizIndex(ctx, remote, body)
	if err != nil {
		return nil, err
	}
	if action == "link" {
		// AI validates the proposed node against its owning course; LMS is the only
		// writer of question attribution. Never auto-merge concepts here.
		var resolved struct {
			NodeID int64 `json:"node_id"`
		}
		if err = json.Unmarshal(result, &resolved); err != nil || resolved.NodeID <= 0 {
			return nil, fmt.Errorf("invalid node resolution")
		}
		if err = s.quizRepo.SetQuizQuestionNode(ctx, quizID, request.QuestionID, resolved.NodeID, request.SourceHash); err != nil {
			return nil, err
		}
	}
	return result, nil
}
