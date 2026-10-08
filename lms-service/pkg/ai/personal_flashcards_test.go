package ai

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestPersonalFlashcardUpstreamErrors(t *testing.T) {
	for _, tc := range []struct {
		body         string
		status, want int
		code         string
	}{
		{`{"detail":"Not Found"}`, 404, 502, "flashcard_endpoint_missing"},
		{`404 page not found`, 404, 502, "flashcard_endpoint_missing"},
		{`{"detail":{"code":"flashcard_not_found","message":"Không tìm thấy thẻ"}}`, 404, 404, "flashcard_not_found"},
		{`{"detail":{"code":"flashcard_schema_pending","message":"Đang cập nhật"}}`, 503, 503, "flashcard_schema_pending"},
		{`private upstream traceback`, 500, 502, "flashcard_upstream_unavailable"},
	} {
		t.Run(tc.code+tc.body[:3], func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/ai/flashcards/personal" {
					t.Error(r.URL.Path)
				}
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(tc.body))
			}))
			defer server.Close()
			client := &Client{baseURL: server.URL + "/", httpClient: server.Client()}
			_, err := client.PersonalFlashcardAction(context.Background(), 2, 74, "list", nil)
			failure, ok := err.(*PersonalFlashcardError)
			if !ok || failure.Status != tc.want || failure.Code != tc.code {
				t.Fatalf("got %#v", err)
			}
		})
	}
}
