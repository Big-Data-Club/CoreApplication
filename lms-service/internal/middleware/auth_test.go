package middleware

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"

	"example/hello/pkg/logger"
)

type fakeRoles struct {
	roles []string
	err   error
}

func (f fakeRoles) GetUserRoles(context.Context, int64) ([]string, error) { return f.roles, f.err }
func testJWT(t *testing.T) string {
	t.Helper()
	raw, err := jwt.NewWithClaims(jwt.SigningMethodHS256, Claims{UserID: 41, Roles: []string{"ADMIN"}, RegisteredClaims: jwt.RegisteredClaims{ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour))}}).SignedString([]byte(strings.Repeat("k", 32)))
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
func TestInternalCallbacksRejectBrowserJWT(t *testing.T) {
	gin.SetMode(gin.TestMode)
	secret := strings.Repeat("s", 32)
	for _, tc := range []struct {
		name, value string
		want        int
	}{{"none", "", 401}, {"browser JWT", testJWT(t), 401}, {"service", secret, 204}} {
		t.Run(tc.name, func(t *testing.T) {
			r := gin.New()
			r.POST("/callback", ServiceOnlyMiddleware(secret), func(c *gin.Context) { c.Status(204) })
			req := httptest.NewRequest("POST", "/callback", nil)
			if tc.name == "browser JWT" {
				req.Header.Set("Authorization", "Bearer "+tc.value)
			} else {
				req.Header.Set("X-API-Secret", tc.value)
			}
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)
			if w.Code != tc.want {
				t.Fatalf("status=%d want=%d", w.Code, tc.want)
			}
		})
	}
	if validServiceSecret("None", "None") {
		t.Fatal("placeholder service secret accepted")
	}
}
func TestLocalRolesDoNotFallBackToJWT(t *testing.T) {
	logger.Init("test")
	for _, tc := range []struct {
		name   string
		reader fakeRoles
		want   int
	}{{"revoked", fakeRoles{}, 403}, {"unavailable", fakeRoles{err: errors.New("db unavailable")}, 503}, {"student overrides token admin", fakeRoles{roles: []string{"STUDENT"}}, 204}} {
		t.Run(tc.name, func(t *testing.T) {
			r := gin.New()
			r.GET("/", AuthMiddleware(strings.Repeat("k", 32)), LoadLocalRoles(tc.reader, nil), func(c *gin.Context) {
				if c.GetString("user_role") != "STUDENT" {
					t.Error("token roles were retained")
				}
				c.Status(204)
			})
			req := httptest.NewRequest(http.MethodGet, "/", nil)
			req.Header.Set("Authorization", "Bearer "+testJWT(t))
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)
			if w.Code != tc.want {
				t.Fatalf("status=%d want=%d", w.Code, tc.want)
			}
		})
	}
}

func TestFileIdentityPreservesLocalRolesAndStrictUpload(t *testing.T) {
	jwtSecret := strings.Repeat("k", 32)
	serviceSecret := strings.Repeat("s", 32)
	for _, tc := range []struct {
		name                        string
		user, service, allowService bool
		want                        int
	}{
		{"JWT local role retained", true, false, false, 204},
		{"service cannot use JWT-only upload", false, true, false, 401},
		{"service can request authorized presign", false, true, true, 204},
	} {
		t.Run(tc.name, func(t *testing.T) {
			r := gin.New()
			r.GET("/", OptionalIdentity(jwtSecret, serviceSecret), LoadLocalRoles(fakeRoles{roles: []string{"STUDENT"}}, nil), RequireIdentity(tc.allowService), func(c *gin.Context) {
				if tc.user && c.GetString("user_role") != "STUDENT" {
					t.Error("token role overwrote local authority")
				}
				c.Status(204)
			})
			req := httptest.NewRequest("GET", "/", nil)
			if tc.user {
				req.Header.Set("Authorization", "Bearer "+testJWT(t))
			}
			if tc.service {
				req.Header.Set("X-API-Secret", serviceSecret)
			}
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)
			if w.Code != tc.want {
				t.Fatalf("status=%d", w.Code)
			}
		})
	}
}
