package game

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestLMSQuestionUsesInternalSecretAndKeepsAnswerServerSide(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Secret") != "internal-secret" || r.URL.Query().Get("user_id") != "41" || r.URL.Query().Get("kind") != "quiz" || r.URL.Query().Get("exclude") != "old" {
			t.Errorf("unexpected LMS request: %s", r.URL)
			w.WriteHeader(http.StatusForbidden)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"id": "lms:quiz:7", "kind": "quiz", "prompt": "Câu hỏi LMS", "options": []string{"Sai", "Đúng"}, "answer": "1", "course_id": 9})
	}))
	defer server.Close()
	client := NewLMSClient(server.URL, "internal-secret")
	q, err := client.Question(context.Background(), 41, "quiz", "old")
	if err != nil || q.Answer != "1" || q.CourseID != 9 {
		t.Fatalf("LMS question: %+v %v", q, err)
	}
}
