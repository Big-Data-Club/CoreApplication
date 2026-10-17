package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestFarmLearningRejectsBrowserWithoutInternalSecret(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := NewFarmLearningHandler(nil, "private-service-secret")
	r := gin.New()
	g := r.Group("/internal/farm", h.Authenticate)
	g.GET("/question", h.Question)
	for _, supplied := range []string{"", "wrong"} {
		req := httptest.NewRequest(http.MethodGet, "/internal/farm/question?user_id=41&kind=quiz", nil)
		if supplied != "" {
			req.Header.Set("X-API-Secret", supplied)
		}
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		if w.Code != http.StatusUnauthorized {
			t.Fatalf("secret %q: status %d", supplied, w.Code)
		}
	}
}
