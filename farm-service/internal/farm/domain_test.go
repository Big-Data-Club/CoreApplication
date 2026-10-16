package farm

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var epoch = time.Date(2026, 10, 17, 10, 0, 0, 0, time.UTC)

func mature(t *testing.T, s *State, id int) *Challenge {
	t.Helper()
	if err := s.Care(id, epoch); err != nil {
		t.Fatal(err)
	}
	c, err := s.Start(id, "quiz", epoch.Add(10*time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	return c
}
func TestHarvestGuardsAndPublicState(t *testing.T) {
	s := NewState()
	if _, err := s.Start(1, "quiz", epoch); err == nil {
		t.Fatal("unwatered crop opened challenge")
	}
	if err := s.Care(0, epoch); err == nil {
		t.Fatal("invalid plot accepted")
	}
	if err := s.Care(1, epoch); err != nil {
		t.Fatal(err)
	}
	ready := *s.Plots[0].ReadyAt
	if err := s.Care(1, epoch.Add(time.Second)); err == nil {
		t.Fatal("watering twice speeds growth")
	}
	if _, err := s.Start(1, "quiz", ready.Add(-time.Second)); err == nil {
		t.Fatal("early harvest")
	}
	if _, err := s.Start(1, "unknown", ready); err == nil {
		t.Fatal("invalid challenge kind")
	}
	c, err := s.Start(1, "quiz", ready)
	if err != nil {
		t.Fatal(err)
	}
	reused, _ := s.Start(1, "flashcard", ready)
	if reused.ID != c.ID {
		t.Fatal("challenge rerolled")
	}
	raw, _ := json.Marshal(s.PublicState())
	if strings.Contains(string(raw), `"answer"`) || strings.Contains(string(raw), `"explanation"`) {
		t.Fatal("answer leaked")
	}
	if s.Plots[0].Challenge.Question.Answer == "" {
		t.Fatal("redaction mutated stored answer")
	}
	result, event, err := s.Answer(41, 1, c.ID, c.Question.Answer, ready, "test-secret")
	if err != nil || !result.Correct || result.Awarded != 5 || event == nil {
		t.Fatalf("harvest failed: %+v %v", result, err)
	}
	if _, _, err = s.Answer(41, 1, c.ID, c.Question.Answer, ready, "test-secret"); err == nil {
		t.Fatal("replay rewarded twice")
	}
	if err = s.Care(1, ready.Add(39*time.Second)); err == nil {
		t.Fatal("rest bypass")
	}
	if err = s.Care(1, ready.Add(40*time.Second)); err != nil {
		t.Fatal(err)
	}
}
func TestWrongAnswerExpiryAndDailyCap(t *testing.T) {
	s := NewState()
	c := mature(t, &s, 1)
	now := epoch.Add(10 * time.Minute)
	r, e, err := s.Answer(41, 1, c.ID, "wrong", now, "secret")
	if err != nil || r.Correct || e != nil || s.Plots[0].ReadyAt == nil || s.Earned != 0 {
		t.Fatal("wrong answer changed harvest/reward")
	}
	if _, err = s.Start(1, "quiz", now); err == nil {
		t.Fatal("retry cooldown bypass")
	}
	c, err = s.Start(1, "flashcard", now.Add(30*time.Second))
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err = s.Answer(41, 1, c.ID, c.Question.Answer, c.ExpiresAt, "secret"); err == nil {
		t.Fatal("expired answer accepted")
	}
	c, err = s.Start(1, "flashcard", c.ExpiresAt)
	if err != nil {
		t.Fatal(err)
	}
	s.Day(c.ExpiresAt.Add(-time.Second))
	s.DailyEarned = DailyLimit
	r, e, err = s.Answer(41, 1, c.ID, "  "+strings.ToUpper(c.Question.Answer)+"  ", c.ExpiresAt.Add(-time.Second), "secret")
	if err != nil || !r.Correct || r.Awarded != 0 || e != nil || s.Plots[0].Harvests != 1 {
		t.Fatal("daily cap must allow learning without score")
	}
	s.Day(epoch.Add(24 * time.Hour))
	if s.DailyEarned != 0 {
		t.Fatal("day did not reset")
	}
}
func TestAnimalsAlsoRequireChallenge(t *testing.T) {
	for _, id := range []int{4, 5, 6} {
		s := NewState()
		c := mature(t, &s, id)
		result, _, err := s.Answer(41, id, c.ID, c.Question.Answer, epoch.Add(10*time.Minute), "secret")
		if err != nil || !result.Correct || s.Plots[id-1].Harvests != 1 {
			t.Fatalf("animal %d: %v", id, err)
		}
	}
}
func TestAccessTokenValidation(t *testing.T) {
	secret := strings.Repeat("s", 64)
	claims := Claims{UserID: 41, Roles: []string{"ROLE_USER"}, RegisteredClaims: jwt.RegisteredClaims{ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour))}}
	sign := func(c Claims, key string, method jwt.SigningMethod) string {
		token, _ := jwt.NewWithClaims(method, c).SignedString([]byte(key))
		return "Bearer " + token
	}
	for _, method := range []jwt.SigningMethod{jwt.SigningMethodHS256, jwt.SigningMethodHS384, jwt.SigningMethodHS512} {
		if id, err := Identity(sign(claims, secret, method), secret); err != nil || id != 41 {
			t.Fatal("valid Java-compatible token rejected")
		}
	}
	invalid := []string{"", "Bearer broken", sign(claims, "different", jwt.SigningMethodHS256)}
	claims.Roles = nil
	invalid = append(invalid, sign(claims, secret, jwt.SigningMethodHS256))
	claims.Roles = []string{"ROLE_USER"}
	claims.ExpiresAt = nil
	invalid = append(invalid, sign(claims, secret, jwt.SigningMethodHS256))
	claims.ExpiresAt = jwt.NewNumericDate(time.Now().Add(-time.Hour))
	invalid = append(invalid, sign(claims, secret, jwt.SigningMethodHS256))
	for _, token := range invalid {
		if _, err := Identity(token, secret); err == nil {
			t.Fatal("invalid/refresh token accepted")
		}
	}
}
func TestCatalogAndQuestions(t *testing.T) {
	seen := map[string]bool{}
	for _, q := range questions {
		if seen[q.ID] || q.Answer == "" || q.Explanation == "" {
			t.Fatalf("invalid question %s", q.ID)
		}
		seen[q.ID] = true
	}
	for _, c := range Catalog {
		if c.SourceURL == "" || len(c.Steps) == 0 || c.Environment == "" {
			t.Fatalf("missing learning guide: %s", c.Kind)
		}
	}
}
func TestRewardSignatureContract(t *testing.T) {
	e := Event{Version: 1, EventID: "e41414f3-015c-4b0a-a666-930134b8c541", HarvestID: "e41414f3-015c-4b0a-a666-930134b8c541", UserID: 41, Delta: 5, OccurredAt: "2026-10-17T10:00:00Z"}
	e.Sign("farm-contract-test-secret-32-bytes")
	if e.Signature != "4f783c87a7d791a5424e327a1ffddfcfbf247b2c8d47cd383cb9886d393551cb" {
		t.Fatalf("signature drift: %s", e.Signature)
	}
}
