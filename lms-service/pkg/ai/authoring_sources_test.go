package ai

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestCurriculumGenerationNeverFallsBackToOldNodeRoute(t *testing.T) {
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.URL.Path != "/ai/quiz/generate-from-sources" {
			t.Errorf("scope lost: %s", r.URL.Path)
		}
		var payload GenerateToBankRequest
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Error(err)
			return
		}
		if payload.CourseID != 7 || len(payload.Sources) != 1 || payload.Sources[0].Text != "Canonical material" {
			t.Errorf("source payload lost: %+v", payload)
		}
		w.WriteHeader(http.StatusNotFound) // Older AI version.
	}))
	defer server.Close()
	client := &Client{baseURL: server.URL, secret: "test-only", httpClient: server.Client()}
	_, err := client.GenerateToBank(context.Background(), GenerateToBankRequest{CourseID: 7,
		Sources: []AuthoringSource{{ContentID: 9, Text: "Canonical material"}}})
	if err == nil || calls != 1 {
		t.Fatalf("unexpected fallback: calls=%d err=%v", calls, err)
	}
}
