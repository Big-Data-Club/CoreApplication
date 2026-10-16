package farm

import (
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

type Claims struct {
	UserID int64    `json:"user_id"`
	Roles  []string `json:"roles"`
	jwt.RegisteredClaims
}

func Identity(header, secret string) (int64, error) {
	if !strings.HasPrefix(header, "Bearer ") {
		return 0, errors.New("missing bearer")
	}
	claims := &Claims{}
	_, err := jwt.ParseWithClaims(strings.TrimPrefix(header, "Bearer "), claims, func(t *jwt.Token) (any, error) { return []byte(secret), nil }, jwt.WithValidMethods([]string{"HS256", "HS384", "HS512"}), jwt.WithExpirationRequired())
	// Refresh tokens from Auth have no roles and must not authorize game actions.
	if err != nil || claims.UserID <= 0 || len(claims.Roles) == 0 {
		return 0, errors.New("invalid access token")
	}
	return claims.UserID, nil
}
func Handler(store *Store, secret string) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) { write(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("GET /ready", func(w http.ResponseWriter, r *http.Request) {
		if err := store.Pool.Ping(r.Context()); err != nil {
			write(w, 503, map[string]string{"error": "Database unavailable"})
			return
		}
		write(w, 200, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/api/v1/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		user, err := Identity(r.Header.Get("Authorization"), secret)
		if err != nil {
			write(w, 401, map[string]string{"error": "Phiên đăng nhập không hợp lệ."})
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 4096)
		var value any
		if r.Method == http.MethodGet && r.URL.Path == "/api/v1/farm" {
			value, err = store.Get(r.Context(), user)
		} else {
			parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
			if r.Method != http.MethodPost || len(parts) != 6 || parts[2] != "farm" || parts[3] != "plots" {
				write(w, 404, map[string]string{"error": "Not found"})
				return
			}
			plot, e := strconv.Atoi(parts[4])
			if e != nil || plot < 1 || plot > 6 {
				write(w, 404, map[string]string{"error": "Không tìm thấy ô đất."})
				return
			}
			var input struct {
				Kind        string `json:"kind"`
				ChallengeID string `json:"challenge_id"`
				Answer      string `json:"answer"`
			}
			decoder := json.NewDecoder(r.Body)
			decoder.DisallowUnknownFields()
			if e = decoder.Decode(&input); e != nil {
				write(w, 400, map[string]string{"error": "Dữ liệu không hợp lệ."})
				return
			}
			if e = decoder.Decode(&struct{}{}); e != io.EOF {
				write(w, 400, map[string]string{"error": "Chỉ gửi một JSON object."})
				return
			}
			switch parts[5] {
			case "care":
				value, err = store.Care(r.Context(), user, plot)
			case "challenge":
				value, err = store.Start(r.Context(), user, plot, input.Kind)
			case "answer":
				if _, e = uuid.Parse(input.ChallengeID); e != nil || len(input.Answer) > 512 || strings.TrimSpace(input.Answer) == "" {
					write(w, 400, map[string]string{"error": "Vui lòng nhập câu trả lời hợp lệ."})
					return
				}
				value, err = store.Answer(r.Context(), user, plot, input.ChallengeID, input.Answer)
			default:
				write(w, 404, map[string]string{"error": "Not found"})
				return
			}
		}
		if err != nil {
			var domainErr *Error
			if errors.As(err, &domainErr) {
				write(w, domainErr.Status, map[string]string{"error": domainErr.Message})
				return
			}
			slog.Error("farm request failed", "error", err)
			write(w, 503, map[string]string{"error": "Nông trại đang bận. Vui lòng thử lại."})
			return
		}
		write(w, 200, value)
	})
	return http.TimeoutHandler(mux, 10*time.Second, `{"error":"Request timed out"}`)
}
func write(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
