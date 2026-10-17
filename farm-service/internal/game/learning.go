package game

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"bdc/farm-service/internal/farm"
	"github.com/jackc/pgx/v5"
)

func learningKind(kind string) string { return kind }
func canHarvest(o *gameEntity, action string, now time.Time) error {
	if o == nil {
		return bad(404, "Không tìm thấy cây/vật nuôi")
	}
	if action == "SELL_CHICKEN" {
		if o.Kind != "chicken" || secs(o.CreatedAt, now) < 420 || o.RT.Hunger == 0 || o.RT.Sick || o.RT.Health < 65 {
			return bad(409, "Gà cần trưởng thành, no và khỏe trước khi xuất bán")
		}
	} else if action != "HARVEST" || o.RT.Ready == 0 {
		return bad(409, "Chưa đến lúc thu hoạch")
	}
	if (o.Kind == "frog" || o.Kind == "fish") && (o.RT.Hunger == 0 || o.RT.Sick || !o.Housed || !o.HasOxygen) {
		return bad(409, "Cá/ếch cần no, khỏe và ao có đủ oxy")
	}
	return nil
}
func readLearning(r *http.Request, tx pgx.Tx, user int64, entity, action string) (farm.Plot, error) {
	var p farm.Plot
	var raw []byte
	err := tx.QueryRow(r.Context(), `SELECT state FROM game_learning WHERE user_id=$1 AND entity_id=$2 AND action=$3 FOR UPDATE`, user, entity, action).Scan(&raw)
	if err != nil {
		return p, err
	}
	err = json.Unmarshal(raw, &p)
	return p, err
}
func saveLearning(r *http.Request, tx pgx.Tx, user int64, entity, action string, p farm.Plot) error {
	raw, err := json.Marshal(p)
	if err != nil {
		return err
	}
	_, err = tx.Exec(r.Context(), `INSERT INTO game_learning(user_id,entity_id,action,state) VALUES($1,$2,$3,$4) ON CONFLICT(user_id,entity_id,action) DO UPDATE SET state=EXCLUDED.state`, user, entity, action, raw)
	return err
}
func (s *Server) registerLearning() {
	s.route("POST", "/api/game/challenge", nil, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v struct {
			EntityID string `json:"entityId"`
			Action   string `json:"action"`
			Kind     string `json:"kind"`
		}
		if err := decode(r, &v); err != nil {
			return err
		}
		if !validUUID(v.EntityID) {
			return bad(400, "Mã vật phẩm không hợp lệ")
		}
		var challenge *farm.Challenge
		err := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if e := activeWorker(g); e != nil {
				return e
			}
			o := g.entity(v.EntityID)
			if e := canHarvest(o, v.Action, g.Now); e != nil {
				return e
			}
			p, e := readLearning(r, tx, u.ID, v.EntityID, v.Action)
			if e != nil && !errors.Is(e, pgx.ErrNoRows) {
				return e
			}
			p.ID = 1
			p.Kind = learningKind(o.Kind)
			ready := g.Now
			p.ReadyAt = &ready
			state := farm.State{Plots: []farm.Plot{p}}
			challenge, e = state.Start(1, v.Kind, g.Now)
			if e != nil {
				return e
			}
			if e = saveLearning(r, tx, u.ID, v.EntityID, v.Action, state.Plots[0]); e != nil {
				return e
			}
			challenge = state.PublicState().Plots[0].Challenge
			return nil
		})
		if err != nil {
			return err
		}
		write(w, 200, challenge)
		return nil
	})
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
	if event != nil {
		raw, _ = json.Marshal(event)
		_, err = tx.Exec(r.Context(), `INSERT INTO farm_outbox(event_id,user_id,payload) VALUES($1,$2,$3)`, event.EventID, u.ID, raw)
	}
	return result, false, err
}
