// Package farm adapts XanhMarket's server-clock crop / rest / rewater loop.
// Farm state and rewards are authoritative here, never in the browser.
package farm

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"golang.org/x/text/unicode/norm"
)

const Reward = 5
const DailyLimit = 100
const Topic = "farm.harvest.reward.v1"

//go:embed questions.json
var questionData []byte

type Question struct {
	ID          string   `json:"id"`
	Kind        string   `json:"kind"`
	Prompt      string   `json:"prompt"`
	Species     string   `json:"species,omitempty"`
	Options     []string `json:"options,omitempty"`
	Answer      string   `json:"answer,omitempty"`
	Explanation string   `json:"explanation,omitempty"`
}

var questions = func() []Question {
	var q []Question
	if err := json.Unmarshal(questionData, &q); err != nil {
		panic(err)
	}
	return q
}()

type Species struct {
	Kind        string   `json:"kind"`
	Label       string   `json:"label"`
	Seconds     int      `json:"seconds"`
	Category    string   `json:"category"`
	Care        string   `json:"care"`
	Product     string   `json:"product"`
	Environment string   `json:"environment"`
	Steps       []string `json:"steps"`
	Fact        string   `json:"fact"`
	SourceTitle string   `json:"source_title"`
	SourceURL   string   `json:"source_url"`
}

//go:embed catalog.json
var catalogData []byte
var Catalog = func() []Species {
	var c []Species
	if err := json.Unmarshal(catalogData, &c); err != nil {
		panic(err)
	}
	return c
}()

type Challenge struct {
	ID        string    `json:"id"`
	Question  Question  `json:"question"`
	ExpiresAt time.Time `json:"expires_at"`
}
type Plot struct {
	ID           int        `json:"id"`
	Kind         string     `json:"kind"`
	ReadyAt      *time.Time `json:"ready_at"`
	RestUntil    time.Time  `json:"rest_until"`
	RetryAt      time.Time  `json:"retry_at"`
	Harvests     int        `json:"harvests"`
	Challenge    *Challenge `json:"challenge,omitempty"`
	LastQuestion string     `json:"last_question,omitempty"`
}
type State struct {
	Plots       []Plot `json:"plots"`
	Earned      int    `json:"earned"`
	RewardDay   string `json:"reward_day"`
	DailyEarned int    `json:"daily_earned"`
}
type Event struct {
	Version    int    `json:"version"`
	EventID    string `json:"event_id"`
	HarvestID  string `json:"harvest_id"`
	UserID     int64  `json:"user_id"`
	Delta      int    `json:"delta"`
	OccurredAt string `json:"occurred_at"`
	Signature  string `json:"signature"`
}
type Result struct {
	Correct     bool   `json:"correct"`
	Explanation string `json:"explanation"`
	Awarded     int    `json:"awarded"`
	EventID     string `json:"event_id,omitempty"`
}
type Error struct {
	Status  int
	Message string
}

func (e *Error) Error() string { return e.Message }
func bad(message string) error { return &Error{409, message} }

func NewState() State {
	s := State{Plots: make([]Plot, 6)}
	for i := range s.Plots {
		s.Plots[i] = Plot{ID: i + 1, Kind: Catalog[i%len(Catalog)].Kind}
	}
	return s
}
func (s *State) Day(now time.Time) {
	day := now.UTC().Format("2006-01-02")
	if s.RewardDay != day {
		s.RewardDay = day
		s.DailyEarned = 0
	}
}
func (s *State) plot(id int) (*Plot, error) {
	if id < 1 || id > len(s.Plots) {
		return nil, &Error{404, "Không tìm thấy ô đất."}
	}
	return &s.Plots[id-1], nil
}
func (s *State) Care(id int, now time.Time) error {
	p, err := s.plot(id)
	if err != nil {
		return err
	}
	if p.ReadyAt != nil {
		return bad("Ô này đã được chăm sóc. Chờ thu hoạch nhé.")
	}
	if now.Before(p.RestUntil) {
		return bad("Ô này đang nghỉ sau thu hoạch.")
	}
	for _, c := range Catalog {
		if c.Kind == p.Kind {
			ready := now.Add(time.Duration(c.Seconds) * time.Second)
			p.ReadyAt = &ready
			return nil
		}
	}
	return bad("Loại cây không hợp lệ.")
}
func (s *State) Start(id int, kind string, now time.Time) (*Challenge, error) {
	p, err := s.plot(id)
	if err != nil {
		return nil, err
	}
	if kind != "quiz" && kind != "flashcard" {
		return nil, &Error{400, "Chọn quiz hoặc flashcard."}
	}
	if p.ReadyAt == nil || now.Before(*p.ReadyAt) {
		return nil, bad("Ô này chưa sẵn sàng thu hoạch.")
	}
	if now.Before(p.RetryAt) {
		return nil, bad("Đợi 30 giây rồi thử câu mới nhé.")
	}
	if p.Challenge != nil && now.Before(p.Challenge.ExpiresAt) {
		return p.Challenge, nil
	}
	candidates := []Question{}
	for _, q := range questions {
		if q.Kind == kind && q.ID != p.LastQuestion && (q.Species == "" || q.Species == p.Kind) {
			candidates = append(candidates, q)
		}
	}
	n, err := rand.Int(rand.Reader, big.NewInt(int64(len(candidates))))
	if err != nil {
		return nil, err
	}
	q := candidates[n.Int64()]
	p.LastQuestion = q.ID
	// Persist the answer snapshot so a catalogue deployment cannot change an open challenge.
	p.Challenge = &Challenge{ID: uuid.NewString(), Question: q, ExpiresAt: now.Add(10 * time.Minute)}
	return p.Challenge, nil
}
func normalize(s string) string {
	return strings.ToLower(strings.Join(strings.Fields(norm.NFC.String(s)), " "))
}
func (s *State) Answer(user int64, id int, challengeID, answer string, now time.Time, secret string) (Result, *Event, error) {
	p, err := s.plot(id)
	if err != nil {
		return Result{}, nil, err
	}
	c := p.Challenge
	if c == nil || c.ID != challengeID || !now.Before(c.ExpiresAt) {
		return Result{}, nil, bad("Câu hỏi đã hết hạn hoặc đã được trả lời. Mở lại ô đất nhé.")
	}
	if p.ReadyAt == nil || now.Before(*p.ReadyAt) {
		return Result{}, nil, bad("Ô này chưa sẵn sàng thu hoạch.")
	}
	result := Result{Correct: normalize(answer) == normalize(c.Question.Answer), Explanation: c.Question.Explanation}
	p.Challenge = nil // A challenge is single use, including wrong answers.
	if !result.Correct {
		p.RetryAt = now.Add(30 * time.Second)
		return result, nil, nil
	}
	s.Day(now)
	p.ReadyAt = nil
	p.RestUntil = now.Add(40 * time.Second)
	p.Harvests++
	if s.DailyEarned >= DailyLimit {
		return result, nil, nil
	}
	result.Awarded = Reward
	result.EventID = c.ID
	s.Earned += Reward
	s.DailyEarned += Reward
	event := &Event{Version: 1, EventID: c.ID, HarvestID: c.ID, UserID: user, Delta: Reward, OccurredAt: now.UTC().Format(time.RFC3339Nano)}
	event.Sign(secret)
	return result, event, nil
}
func (e *Event) Sign(secret string) {
	mac := hmac.New(sha256.New, []byte(secret))
	fmt.Fprint(mac, strings.Join([]string{e.EventID, strconv.FormatInt(e.UserID, 10), e.HarvestID, strconv.Itoa(e.Delta), e.OccurredAt, "1"}, "|"))
	e.Signature = hex.EncodeToString(mac.Sum(nil))
}

// PublicState strips both answers and explanations before sending open challenges.
func (s State) PublicState() State {
	s.Plots = append([]Plot(nil), s.Plots...)
	for i := range s.Plots {
		if s.Plots[i].Challenge != nil {
			c := *s.Plots[i].Challenge
			c.Question.Answer = ""
			c.Question.Explanation = ""
			s.Plots[i].Challenge = &c
		}
	}
	return s
}
