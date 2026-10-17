// Package game ports XanhMarket's playable economy without real-farm integration.
package game

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"unicode/utf8"

	"bdc/farm-service/internal/farm"
	domain "bdc/farm-service/internal/gamedomain"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed schema.sql
var schema string

type User struct{ ID int64 }
type Server struct {
	DB     *pgxpool.Pool
	Store  *farm.Store
	LMS    *LMSClient
	mux    *http.ServeMux
	secret string
}
type worldFarm struct {
	ID    string `json:"id"`
	Name  string `json:"name"`
	Coins int    `json:"coins"`
	XP    int    `json:"xp"`
	Level int    `json:"level"`
}

func Migrate(ctx context.Context, pool *pgxpool.Pool) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(734620118)"); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, schema); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func Handler(store *farm.Store, secret string) http.Handler {
	return HandlerWithLMS(store, secret, nil)
}
func HandlerWithLMS(store *farm.Store, secret string, lms *LMSClient) http.Handler {
	s := &Server{DB: store.Pool, Store: store, LMS: lms, mux: http.NewServeMux(), secret: secret}
	s.registerEconomy()
	s.registerLearning()
	return s.mux
}
func (s *Server) route(method, path string, _ []string, fn func(http.ResponseWriter, *http.Request, User) error) {
	path = strings.Replace(path, "/api/game/", "/api/v1/farm/game/", 1)
	s.mux.HandleFunc(method+" "+path, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		id, err := farm.Identity(r.Header.Get("Authorization"), s.secret)
		if err != nil {
			write(w, 401, map[string]string{"error": "Vui lòng đăng nhập lại."})
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 4096)
		if err = fn(w, r, User{ID: id}); err != nil {
			var known *farm.Error
			if errors.As(err, &known) {
				write(w, known.Status, map[string]string{"error": known.Message})
				return
			}
			slog.Error("game request failed", "path", r.URL.Path, "error", err)
			write(w, 500, map[string]string{"error": "Không thể tải nông trại. Vui lòng thử lại."})
		}
	})
}
func (s *Server) tx(ctx context.Context, fn func(pgx.Tx) error) error {
	tx, e := s.DB.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if e = fn(tx); e != nil {
		return e
	}
	return tx.Commit(ctx)
}
func (s *Server) farmTx(r *http.Request, tx pgx.Tx, user int64, _ bool) (worldFarm, error) {
	var f worldFarm
	_, err := tx.Exec(r.Context(), `INSERT INTO virtual_farms(id,owner_id,name) VALUES($1,$2,'Nông trại kiến thức') ON CONFLICT(owner_id) DO NOTHING`, newID(), user)
	if err != nil {
		return f, err
	}
	err = tx.QueryRow(r.Context(), `SELECT id::text,name,coins,xp FROM virtual_farms WHERE owner_id=$1 FOR UPDATE`, user).Scan(&f.ID, &f.Name, &f.Coins, &f.XP)
	f.Level = domain.Level(f.XP)
	return f, err
}
func newID() string           { return uuid.NewString() }
func validUUID(v string) bool { _, e := uuid.Parse(v); return e == nil }
func bad(status int, format string, args ...any) error {
	return &farm.Error{Status: status, Message: fmt.Sprintf(format, args...)}
}
func write(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func success(w http.ResponseWriter, message string) {
	write(w, 200, map[string]string{"message": message})
}
func decode(r *http.Request, v any) error {
	d := json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	if err := d.Decode(v); err != nil {
		return bad(400, "Dữ liệu không hợp lệ")
	}
	if err := d.Decode(&struct{}{}); err != io.EOF {
		return bad(400, "Chỉ gửi một JSON object")
	}
	return nil
}
func clean(v string, max int) string {
	v = strings.TrimSpace(v)
	if !utf8.ValidString(v) {
		return ""
	}
	r := []rune(v)
	if len(r) > max {
		return string(r[:max])
	}
	return v
}
