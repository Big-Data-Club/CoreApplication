package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"example/hello/pkg/logger"
	"fmt"
	"io"
	"net/http"
	"strings"
)

type PersonalFlashcardError struct {
	Status  int
	Code    string
	Message string
}

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
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(c.baseURL, "/")+"/ai/flashcards/personal", bytes.NewReader(raw))
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
		failure := &PersonalFlashcardError{Status: http.StatusBadGateway, Code: "flashcard_upstream_unavailable", Message: "Chưa kết nối được kho thẻ. Hãy thử lại sau ít phút."}
		var body struct {
			Detail json.RawMessage `json:"detail"`
		}
		_ = json.NewDecoder(io.LimitReader(resp.Body, 8192)).Decode(&body)
		var detail struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		}
		_ = json.Unmarshal(body.Detail, &detail)
		switch detail.Code {
		case "invalid_request", "flashcard_not_found", "flashcard_schema_pending", "flashcard_unavailable":
			failure.Status, failure.Code, failure.Message = resp.StatusCode, detail.Code, detail.Message
		default:
			if resp.StatusCode == http.StatusNotFound {
				// Missing AI route is a deployment failure, not a missing learner card.
				failure.Code = "flashcard_endpoint_missing"
				failure.Message = "Kho thẻ chưa sẵn sàng. Hãy thử lại sau ít phút."
			}
		}
		logger.Warn("AI personal library request failed", map[string]interface{}{"action": action, "upstream_status": resp.StatusCode, "code": failure.Code})
		return nil, failure
	}
	var result map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&result)
	return result, err
}
