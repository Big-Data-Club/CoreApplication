package ai

import (
	"context"
	"encoding/json"
	"fmt"
)

// QuizIndex is internal-only; the LMS resolves quiz/course/user scope first.
func (c *Client) QuizIndex(ctx context.Context, action string, body interface{}) (json.RawMessage, error) {
	switch action {
	case "queue", "state", "search", "node", "suggest":
	default:
		return nil, fmt.Errorf("invalid quiz index action")
	}
	var result json.RawMessage
	err := c.post(ctx, "/ai/quiz-index/"+action, body, &result)
	return result, err
}
