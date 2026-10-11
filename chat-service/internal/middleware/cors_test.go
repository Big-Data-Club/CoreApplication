package middleware

import (
	"net/http/httptest"
	"testing"
)

func TestWebSocketOrigin(t *testing.T) {
	allowed := WebSocketOrigin([]string{" https://bdc.example "})
	for _, step := range []struct {
		origin string
		want   bool
	}{{"", true}, {"https://bdc.example", true}, {"https://bdc.example.evil", false}, {"null", false}, {"https://evil.example", false}} {
		r := httptest.NewRequest("GET", "/chat/ws", nil)
		r.Header.Set("Origin", step.origin)
		if allowed(r) != step.want {
			t.Fatalf("origin %q", step.origin)
		}
	}
}
