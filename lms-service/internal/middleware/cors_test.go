package middleware

import (
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"example/hello/internal/config"
)

func TestCORSRejectsUntrustedMutationOrigins(t *testing.T) {
	for _, tc := range []struct {
		name, origin, site string
		want               int
	}{{"trusted", "https://app.example.invalid", "same-origin", 204}, {"untrusted", "https://evil.example.invalid", "cross-site", 403}, {"missing cross site origin", "", "cross-site", 403}, {"service client", "", "", 204}} {
		t.Run(tc.name, func(t *testing.T) {
			r := gin.New()
			r.Use(CORS(config.CORSConfig{AllowedOrigins: []string{"https://app.example.invalid"}, AllowCredentials: true}))
			r.POST("/", func(c *gin.Context) { c.Status(204) })
			req := httptest.NewRequest("POST", "/", nil)
			req.Header.Set("Origin", tc.origin)
			req.Header.Set("Sec-Fetch-Site", tc.site)
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)
			if w.Code != tc.want {
				t.Fatalf("status=%d", w.Code)
			}
		})
	}
}
