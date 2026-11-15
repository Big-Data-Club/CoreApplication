package handler

import (
	"bytes"
	"context"
	"io"
	"mime/multipart"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"example/hello/internal/config"
	"example/hello/pkg/storage"
)

type uploadAccess struct {
	registered int
	public     bool
}

func (a *uploadAccess) Register(_ context.Context, _ string, _ int64, _ int64, public bool) error {
	a.registered++
	a.public = public
	return nil
}
func (a *uploadAccess) Forget(context.Context, string) error { return nil }
func (a *uploadAccess) Authorize(context.Context, string, int64, string, bool, bool) error {
	return nil
}
func uploadRequest(t *testing.T, data, visibility string) (*bytes.Buffer, string) {
	t.Helper()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	if visibility != "" {
		if err := writer.WriteField("visibility", visibility); err != nil {
			t.Fatal(err)
		}
	}
	part, err := writer.CreateFormFile("file", "fixture.txt")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := io.WriteString(part, data); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return &body, writer.FormDataContentType()
}
func TestUploadStopsOversizedFileBeforeStorage(t *testing.T) {
	gin.SetMode(gin.TestMode)
	dir := t.TempDir()
	store, err := storage.NewLocalStorage(dir)
	if err != nil {
		t.Fatal(err)
	}
	access := &uploadAccess{}
	handler := NewFileHandler(store, config.UploadConfig{MaxSize: 16}, access)
	r := gin.New()
	r.POST("/upload", func(c *gin.Context) { c.Set("user_id", int64(41)); handler.UploadFile(c) })
	body, contentType := uploadRequest(t, strings.Repeat("x", 64), "")
	req := httptest.NewRequest("POST", "/upload", body)
	req.Header.Set("Content-Type", contentType)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if w.Code != 413 || access.registered != 0 || len(entries) > 0 {
		t.Fatalf("status=%d registered=%d stored=%d", w.Code, access.registered, len(entries))
	}
}
func TestUploadRegistersPrivateByDefault(t *testing.T) {
	dir := t.TempDir()
	store, err := storage.NewLocalStorage(dir)
	if err != nil {
		t.Fatal(err)
	}
	access := &uploadAccess{}
	handler := NewFileHandler(store, config.UploadConfig{MaxSize: 1024}, access)
	r := gin.New()
	r.POST("/upload", func(c *gin.Context) { c.Set("user_id", int64(41)); handler.UploadFile(c) })
	body, contentType := uploadRequest(t, "fixture", "")
	req := httptest.NewRequest("POST", "/upload", body)
	req.Header.Set("Content-Type", contentType)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != 200 || access.registered != 1 || access.public {
		t.Fatalf("status=%d registered=%d public=%v body=%s", w.Code, access.registered, access.public, w.Body)
	}
}
