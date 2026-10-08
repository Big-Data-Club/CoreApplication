package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
)

type PersonalFlashcardError struct{ Status int }

func (e *PersonalFlashcardError) Error() string {
	return fmt.Sprintf("personal flashcard status %d", e.Status)
}

func (c *Client) PersonalFlashcardAction(ctx context.Context, studentID, courseID int64, action string, data map[string]interface{}) (map[string]interface{}, error) {
	raw, err := json.Marshal(map[string]interface{}{"student_id": studentID, "course_id": courseID, "action": action, "data": data})
	if err != nil {
		return nil, err
	}
	if data == nil {
		raw, _ = json.Marshal(map[string]interface{}{"student_id": studentID, "course_id": courseID, "action": action, "data": map[string]interface{}{}})
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/ai/flashcards/personal", bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-AI-Secret", c.secret)
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		status := http.StatusBadGateway
		if resp.StatusCode == 400 || resp.StatusCode == 404 {
			status = resp.StatusCode
		}
		return nil, &PersonalFlashcardError{Status: status}
	}
	var result map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&result)
	return result, err
}
