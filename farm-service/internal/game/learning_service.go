package game

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"bdc/farm-service/internal/farm"
	"bdc/farm-service/internal/game/service"
	"github.com/jackc/pgx/v5"
)

func learningKind(kind string) string { return kind }
func canHarvest(o *gameEntity, action string, now time.Time) error {
	if o == nil {
		return bad(404, "Không tìm thấy cây/vật nuôi")
	}
	if reason := service.HarvestViolation(service.HarvestSubject{
		Kind: o.Kind, AgeSeconds: secs(o.CreatedAt, now), Ready: o.RT.Ready,
		Hunger: o.RT.Hunger, Sick: o.RT.Sick, Health: o.RT.Health,
		Housed: o.Housed, HasOxygen: o.HasOxygen,
	}, action); reason != "" {
		return bad(409, "%s", reason)
	}
	return nil
}

// Grade, receipt, inventory changes and outbox are committed in the SAME game
// transaction. A replay never harvests again, even after a lost HTTP response.
func (s *Server) gradeHarvest(r *http.Request, tx pgx.Tx, g *gameTx, u User, entity, action, id, answer string) (farm.Result, bool, error) {
	var result farm.Result
	if !validUUID(id) {
		return result, false, bad(409, "Cần trả lời câu hỏi trước khi thu hoạch")
	}
	var raw []byte
	err := tx.QueryRow(r.Context(), `SELECT a.result FROM farm_answers a JOIN game_harvest_receipts g ON g.challenge_id=a.challenge_id WHERE g.challenge_id=$1 AND g.user_id=$2 AND g.entity_id=$3 AND g.action=$4`, id, u.ID, entity, action).Scan(&raw)
	if err == nil {
		err = json.Unmarshal(raw, &result)
		return result, true, err
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return result, false, err
	}
	p, err := readLearning(r, tx, u.ID, entity, action)
	if errors.Is(err, pgx.ErrNoRows) {
		return result, false, bad(409, "Hãy mở câu hỏi thu hoạch trước")
	}
	if err != nil {
		return result, false, err
	}
	if err = canHarvest(g.entity(entity), action, g.Now); err != nil {
		return result, false, err
	}
	initial, _ := json.Marshal(farm.NewState())
	if _, err = tx.Exec(r.Context(), `INSERT INTO farm_states(user_id,state) VALUES($1,$2) ON CONFLICT DO NOTHING`, u.ID, initial); err != nil {
		return result, false, err
	}
	if err = tx.QueryRow(r.Context(), `SELECT state FROM farm_states WHERE user_id=$1 FOR UPDATE`, u.ID).Scan(&raw); err != nil {
		return result, false, err
	}
	var totals farm.State
	if err = json.Unmarshal(raw, &totals); err != nil {
		return result, false, err
	}
	grading := totals
	grading.Plots = []farm.Plot{p}
	grading.Day(g.Now)
	question := p.Challenge
	result, event, err := grading.Answer(u.ID, 1, id, answer, g.Now, s.Store.Secret)
	if err != nil {
		return result, false, err
	}
	p = grading.Plots[0]
	if err = saveLearning(r, tx, u.ID, entity, action, p); err != nil {
		return result, false, err
	}
	totals.Earned = grading.Earned
	totals.DailyEarned = grading.DailyEarned
	totals.RewardDay = grading.RewardDay
	raw, _ = json.Marshal(totals)
	if _, err = tx.Exec(r.Context(), `UPDATE farm_states SET state=$2,updated_at=$3 WHERE user_id=$1`, u.ID, raw, g.Now); err != nil {
		return result, false, err
	}
	raw, _ = json.Marshal(result)
	if _, err = tx.Exec(r.Context(), `INSERT INTO farm_answers(challenge_id,user_id,result) VALUES($1,$2,$3)`, id, u.ID, raw); err != nil {
		return result, false, err
	}
	if _, err = tx.Exec(r.Context(), `INSERT INTO game_harvest_receipts(challenge_id,user_id,entity_id,action) VALUES($1,$2,$3,$4)`, id, u.ID, entity, action); err != nil {
		return result, false, err
	}
	if question != nil && question.Question.CourseID > 0 {
		attempt := map[string]any{"challenge_id": id, "user_id": u.ID, "course_id": question.Question.CourseID, "node_id": question.Question.NodeID, "source_id": question.Question.ID, "kind": question.Question.Kind, "correct": result.Correct}
		raw, _ = json.Marshal(attempt)
		if _, err = tx.Exec(r.Context(), `INSERT INTO game_learning_outbox(challenge_id,payload) VALUES($1,$2)`, id, raw); err != nil {
			return result, false, err
		}
	}
	if event != nil {
		raw, _ = json.Marshal(event)
		_, err = tx.Exec(r.Context(), `INSERT INTO farm_outbox(event_id,user_id,payload) VALUES($1,$2,$3)`, event.EventID, u.ID, raw)
	}
	return result, false, err
}
