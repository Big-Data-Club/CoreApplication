package game

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestLMSQuestionUsesInternalSecretAndKeepsAnswerServerSide(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Secret") != "internal-secret" || r.URL.Query().Get("user_id") != "41" || r.URL.Query().Get("kind") != "quiz" || r.URL.Query().Get("exclude") != "old" {
			t.Errorf("unexpected LMS request: %s", r.URL)
			w.WriteHeader(http.StatusForbidden)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"id": "lms:quiz:7", "kind": "quiz", "prompt": strings.Repeat("x", 9000), "images": []map[string]string{{"url": "https://example.com/question.png", "position": "below_question"}}, "option_images": []any{nil, map[string]string{"url": "https://example.com/answer.png"}}, "options": []string{"Sai", "Đúng"}, "answer": "1", "course_id": 9})
	}))
	defer server.Close()
	client := NewLMSClient(server.URL, "internal-secret")
	q, err := client.Question(context.Background(), 41, "quiz", "old")
	if err != nil || q.Answer != "1" || q.CourseID != 9 || len(q.Images) != 1 || q.Images[0].Position != "below_question" || len(q.OptionImages) != 2 || q.OptionImages[0] != nil || q.OptionImages[1].URL != "https://example.com/answer.png" {
		t.Fatalf("LMS question: %+v %v", q, err)
	}
}
