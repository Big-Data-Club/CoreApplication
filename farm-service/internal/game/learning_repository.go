package game

import (
	"encoding/json"
	"net/http"

	"bdc/farm-service/internal/farm"
	"github.com/jackc/pgx/v5"
)

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
