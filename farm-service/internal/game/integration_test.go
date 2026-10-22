package game

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"bdc/farm-service/internal/farm"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestPlayableWorldQuizAtomicHarvest(t *testing.T) {
	url := os.Getenv("FARM_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("requires disposable PostgreSQL")
	}
	ctx := context.Background()
	admin, e := pgxpool.New(ctx, url)
	if e != nil {
		t.Fatal(e)
	}
	defer admin.Close()
	schema := "game_test_" + strings.ReplaceAll(uuid.NewString(), "-", "")
	if _, e = admin.Exec(ctx, "CREATE SCHEMA "+schema); e != nil {
		t.Fatal(e)
	}
	defer admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	cfg, e := pgxpool.ParseConfig(url)
	if e != nil {
		t.Fatal(e)
	}
	cfg.ConnConfig.RuntimeParams["search_path"] = schema
	pool, e := pgxpool.NewWithConfig(ctx, cfg)
	if e != nil {
		t.Fatal(e)
	}
	defer pool.Close()
	store := &farm.Store{Pool: pool, Secret: "game-test-signing-secret-32-bytes!"}
	if e = store.Migrate(ctx); e != nil {
		t.Fatal(e)
	}
	if e = Migrate(ctx, pool); e != nil {
		t.Fatal(e)
	}
	if e = Migrate(ctx, pool); e != nil {
		t.Fatal("repeat migration", e)
	}
	secret := "game-test-jwt-secret-32-bytes-long"
	handler := Handler(store, secret)
	call := func(user int64, method, path, body string) *httptest.ResponseRecorder {
		token, _ := jwt.NewWithClaims(jwt.SigningMethodHS256, farm.Claims{UserID: user, Roles: []string{"ROLE_USER"}, RegisteredClaims: jwt.RegisteredClaims{ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour))}}).SignedString([]byte(secret))
		r := httptest.NewRequest(method, "/api/v1/farm/game/"+path, strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	state := call(501, "GET", "state", "")
	if state.Code != 200 {
		t.Fatal(state.Code, state.Body.String())
	}
	var world struct {
		Farm     worldFarm    `json:"farm"`
		Entities []gameEntity `json:"entities"`
		Life     struct {
			NextInsectIn int `json:"nextInsectIn"`
			HungerPct    int `json:"hungerPct"`
		} `json:"life"`
		CareTimers struct {
			FarmerHunger int `json:"farmerHunger"`
			AnimalHunger int `json:"animalHunger"`
			CropWater    int `json:"cropWater"`
		} `json:"careTimers"`
		WildInsects []wildInsect `json:"wildInsects"`
	}
	if e = json.Unmarshal(state.Body.Bytes(), &world); e != nil {
		t.Fatal(e)
	}
	if len(world.Entities) != 3 || world.Farm.Coins != 900 {
		t.Fatal("starter world missing", state.Body.String())
	}
	var careRulesVersion int
	if e = pool.QueryRow(ctx, `SELECT care_rules_version FROM farm_economy WHERE farm_id=$1`, world.Farm.ID).Scan(&careRulesVersion); e != nil {
		t.Fatal(e)
	}
	if careRulesVersion != 2 || world.Life.HungerPct != 100 || world.CareTimers.FarmerHunger != 43200 || world.CareTimers.AnimalHunger != 43200 || world.CareTimers.CropWater != 43200 {
		t.Fatal("new farm did not start with the 12-hour care rules", state.Body.String())
	}
	if world.Life.NextInsectIn < 1 || world.Life.NextInsectIn > 75 || len(world.WildInsects) != 2 || world.WildInsects[0].ExpiresAt.IsZero() {
		t.Fatal("world milestone metadata missing", state.Body.String())
	}
	var crop string
	for _, o := range world.Entities {
		if o.Kind == "rice_crop" {
			crop = o.ID
		}
	}
	if crop == "" {
		t.Fatal("missing rice")
	}
	for _, request := range []struct {
		path, body string
		status     int
	}{
		{"place", `{"kind":"tank","x":12,"y":4}`, 200},
		{"place", `{"kind":"chicken","x":12,"y":4}`, 409},
		{"move", fmt.Sprintf(`{"entityId":%q,"x":7,"y":5}`, crop), 200},
		{"action", fmt.Sprintf(`{"entityId":%q,"action":"WATER"}`, crop), 200},
		{"action", fmt.Sprintf(`{"entityId":%q,"action":"HARVEST"}`, crop), 409},
	} {
		r := call(501, "POST", request.path, request.body)
		if r.Code != request.status {
			t.Fatalf("%s: %d %s", request.path, r.Code, r.Body.String())
		}
	}
	if r := call(502, "POST", "action", fmt.Sprintf(`{"entityId":%q,"action":"WATER"}`, crop)); r.Code != 404 {
		t.Fatal("cross-user access", r.Code)
	}
	_, e = pool.Exec(ctx, `UPDATE entity_runtime SET yield_ready=1,work_seconds=120 WHERE entity_id=$1`, crop)
	if e != nil {
		t.Fatal(e)
	}
	body := fmt.Sprintf(`{"entityId":%q,"action":"HARVEST","kind":"quiz"}`, crop)
	r := call(501, "POST", "challenge", body)
	if r.Code != 200 {
		t.Fatal(r.Code, r.Body.String())
	}
	if strings.Contains(r.Body.String(), `"answer"`) || strings.Contains(r.Body.String(), `"explanation"`) {
		t.Fatal("answer leaked")
	}
	var challenge farm.Challenge
	_ = json.Unmarshal(r.Body.Bytes(), &challenge)
	var raw []byte
	if e = pool.QueryRow(ctx, `SELECT state FROM game_learning WHERE user_id=501 AND entity_id=$1`, crop).Scan(&raw); e != nil {
		t.Fatal(e)
	}
	var learned farm.Plot
	_ = json.Unmarshal(raw, &learned)
	wrong := call(501, "POST", "action", fmt.Sprintf(`{"entityId":%q,"action":"HARVEST","challenge_id":%q,"answer":"wrong"}`, crop, challenge.ID))
	if wrong.Code != 200 || !strings.Contains(wrong.Body.String(), `"correct":false`) {
		t.Fatal("wrong answer", wrong.Code, wrong.Body.String())
	}
	if r = call(501, "POST", "challenge", body); r.Code != 409 {
		t.Fatal("cooldown missing", r.Code)
	}
	// Advance only the stored retry time in this isolated test schema.
	_, e = pool.Exec(ctx, `UPDATE game_learning SET state=jsonb_set(state,'{retry_at}','"2000-01-01T00:00:00Z"') WHERE user_id=501`)
	if e != nil {
		t.Fatal(e)
	}
	r = call(501, "POST", "challenge", body)
	if r.Code != 200 {
		t.Fatal(r.Code, r.Body.String())
	}
	_ = json.Unmarshal(r.Body.Bytes(), &challenge)
	_ = pool.QueryRow(ctx, `SELECT state FROM game_learning WHERE user_id=501 AND entity_id=$1`, crop).Scan(&raw)
	_ = json.Unmarshal(raw, &learned)
	answer := fmt.Sprintf(`{"entityId":%q,"action":"HARVEST","challenge_id":%q,"answer":%q}`, crop, challenge.ID, learned.Challenge.Question.Answer)
	var wg sync.WaitGroup
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			res := call(501, "POST", "action", answer)
			if res.Code != 200 || !strings.Contains(res.Body.String(), `"awarded":5`) {
				t.Errorf("replay %d %s", res.Code, res.Body.String())
			}
		}()
	}
	wg.Wait()
	var qty, events int
	_ = pool.QueryRow(ctx, `SELECT quantity FROM farm_inventory WHERE farm_id=$1 AND kind='paddy'`, world.Farm.ID).Scan(&qty)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM farm_outbox WHERE user_id=501`).Scan(&events)
	if qty != 6 || events != 1 {
		t.Fatalf("duplicate harvest: paddy=%d events=%d", qty, events)
	}
	var ready int
	_ = pool.QueryRow(ctx, `SELECT yield_ready FROM entity_runtime WHERE entity_id=$1`, crop).Scan(&ready)
	if ready != 0 {
		t.Fatal("crop not harvested")
	}
	if res := call(501, http.MethodPost, "place", `{"kind":"rice_crop","x":1,"y":1}`); res.Code != 400 {
		t.Fatal("house placement accepted")
	}
	var chicken string
	for _, o := range world.Entities {
		if o.Kind == "chicken" {
			chicken = o.ID
		}
	}
	if chicken == "" {
		t.Fatal("missing chicken")
	}
	if _, e = pool.Exec(ctx, `UPDATE entity_runtime SET yield_ready=1 WHERE entity_id=$1`, chicken); e != nil {
		t.Fatal(e)
	}
	var delivered int
	var deliveryPool *pgxpool.Pool
	lms := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Secret") != "farm-to-lms-test-secret" {
			w.WriteHeader(401)
			return
		}
		if r.URL.Path == "/api/v1/internal/farm/question" {
			_ = json.NewEncoder(w).Encode(farm.Question{ID: "lms:quiz:7", Kind: "quiz", Prompt: "Lúa cho gì?", Options: []string{"Thóc", "Trứng"}, Answer: "0", CourseID: 9})
			return
		}
		if r.URL.Path == "/api/v1/internal/farm/attempt" {
			// Delivery must not hold the only PostgreSQL connection while waiting for LMS.
			if deliveryPool != nil {
				checkCtx, cancel := context.WithTimeout(r.Context(), 500*time.Millisecond)
				defer cancel()
				var count int
				if err := deliveryPool.QueryRow(checkCtx, `SELECT count(*) FROM game_learning_outbox`).Scan(&count); err != nil {
					t.Errorf("outbox delivery held a database connection: %v", err)
					w.WriteHeader(http.StatusServiceUnavailable)
					return
				}
			}
			var attempt struct {
				ChallengeID string `json:"challenge_id"`
				UserID      int64  `json:"user_id"`
				CourseID    int64  `json:"course_id"`
				Correct     bool   `json:"correct"`
			}
			if json.NewDecoder(r.Body).Decode(&attempt) != nil || attempt.ChallengeID == "" || attempt.UserID != 501 || attempt.CourseID != 9 || attempt.Correct {
				t.Error("invalid learning attempt", attempt)
				w.WriteHeader(400)
				return
			}
			delivered++
			w.WriteHeader(http.StatusNoContent)
			return
		}
		w.WriteHeader(404)
	}))
	defer lms.Close()
	client := NewLMSClient(lms.URL, "farm-to-lms-test-secret")
	handler = HandlerWithLMS(store, secret, client)
	r = call(501, "POST", "challenge", fmt.Sprintf(`{"entityId":%q,"action":"HARVEST","kind":"quiz"}`, chicken))
	if r.Code != 200 || strings.Contains(r.Body.String(), `"answer"`) {
		t.Fatal("LMS challenge", r.Code, r.Body.String())
	}
	var lmsChallenge farm.Challenge
	if e = json.Unmarshal(r.Body.Bytes(), &lmsChallenge); e != nil {
		t.Fatal(e)
	}
	r = call(501, "POST", "action", fmt.Sprintf(`{"entityId":%q,"action":"HARVEST","challenge_id":%q,"answer":"1"}`, chicken, lmsChallenge.ID))
	if r.Code != 200 || !strings.Contains(r.Body.String(), `"correct_answer":"Thóc"`) {
		t.Fatal("wrong LMS answer feedback", r.Code, r.Body.String())
	}
	var pending int
	if e = pool.QueryRow(ctx, `SELECT count(*) FROM game_learning_outbox WHERE delivered_at IS NULL`).Scan(&pending); e != nil || pending != 1 {
		t.Fatal("outbox missing", pending, e)
	}
	deliveryCfg, e := pgxpool.ParseConfig(url)
	if e != nil {
		t.Fatal(e)
	}
	deliveryCfg.ConnConfig.RuntimeParams["search_path"] = schema
	deliveryCfg.MaxConns = 1
	deliveryPool, e = pgxpool.NewWithConfig(ctx, deliveryCfg)
	if e != nil {
		t.Fatal(e)
	}
	defer deliveryPool.Close()
	if sent, e := DispatchLearning(ctx, deliveryPool, client); e != nil || !sent || delivered != 1 {
		t.Fatal("LMS delivery", sent, delivered, e)
	}
	if sent, e := DispatchLearning(ctx, deliveryPool, client); e != nil || sent || delivered != 1 {
		t.Fatal("duplicate LMS delivery", sent, delivered, e)
	}
}
