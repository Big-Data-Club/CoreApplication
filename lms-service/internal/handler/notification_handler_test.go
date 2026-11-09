package handler

import (
	"context"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"

	"example/hello/internal/service"
	"github.com/gin-gonic/gin"
)

type fakeNoticeStore struct {
	user  int64
	calls int
	fail  bool
}

func (f *fakeNoticeStore) Feed(_ context.Context, user int64) (*service.NotificationFeed, error) {
	f.user = user
	f.calls++
	if f.fail {
		return nil, errors.New("private database details")
	}
	return &service.NotificationFeed{Alerts: []service.LearningNotice{}}, nil
}
func (f *fakeNoticeStore) MarkRead(_ context.Context, user int64, _ []string) error {
	f.user = user
	f.calls++
	return nil
}
func (f *fakeNoticeStore) Channels(context.Context, int64) ([]string, error) { return nil, nil }

func noticeRequest(store *fakeNoticeStore, user int64, method, path, body string) *httptest.ResponseRecorder {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(func(c *gin.Context) {
		if user > 0 {
			c.Set("user_id", user)
		}
	})
	h := NewNotificationHandler(store, nil)
	router.GET("/notifications", h.List)
	router.POST("/notifications/read", h.Read)
	router.GET("/notifications/stream", h.Stream)
	recorder := httptest.NewRecorder()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(recorder, req)
	return recorder
}
func TestNotificationsRequireAuthenticatedSubject(t *testing.T) {
	for _, route := range []struct{ method, path string }{{"GET", "/notifications"}, {"POST", "/notifications/read"}, {"GET", "/notifications/stream"}} {
		store := &fakeNoticeStore{}
		response := noticeRequest(store, 0, route.method, route.path, `{"keys":["learning:1"]}`)
		if response.Code != 401 || store.calls != 0 {
			t.Fatalf("unauthorized request reached store: %d", response.Code)
		}
	}
}
func TestNotificationReadInjectsOwnerAndRejectsBadKeys(t *testing.T) {
	store := &fakeNoticeStore{}
	response := noticeRequest(store, 42, "POST", "/notifications/read", `{"user_id":99,"keys":["learning:1"]}`)
	if response.Code != 200 || store.user != 42 {
		t.Fatalf("wrong owner: %d %d", response.Code, store.user)
	}
	store.calls = 0
	response = noticeRequest(store, 42, "POST", "/notifications/read", `{"keys":["bad"]}`)
	if response.Code != 400 || store.calls != 0 {
		t.Fatal("invalid keys reached store")
	}
}
func TestNotificationFailureIsRecoverableWithoutLeakingSQL(t *testing.T) {
	store := &fakeNoticeStore{fail: true}
	response := noticeRequest(store, 42, "GET", "/notifications", "")
	if response.Code != 503 || strings.Contains(response.Body.String(), "database") {
		t.Fatalf("bad failure response: %s", response.Body.String())
	}
}
