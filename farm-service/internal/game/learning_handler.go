package game

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"bdc/farm-service/internal/farm"
	"bdc/farm-service/internal/game/dto"
	"github.com/jackc/pgx/v5"
)

func (s *Server) registerLearning() {
	s.route("POST", "/api/game/challenge", nil, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.ChallengeRequest
		if err := decode(r, &v); err != nil {
			return err
		}
		if !validUUID(v.EntityID) {
			return bad(400, "Mã vật phẩm không hợp lệ")
		}
		if v.Kind != "quiz" && v.Kind != "flashcard" {
			return bad(400, "Chọn quiz hoặc flashcard")
		}
		var lmsQuestion farm.Question
		if s.LMS != nil {
			var raw []byte
			var previous farm.Plot
			if e := s.DB.QueryRow(r.Context(), `SELECT state FROM game_learning WHERE user_id=$1 AND entity_id=$2 AND action=$3`, u.ID, v.EntityID, v.Action).Scan(&raw); e == nil {
				_ = json.Unmarshal(raw, &previous)
			}
			if previous.Challenge != nil && time.Now().Before(previous.Challenge.ExpiresAt) && previous.Challenge.Question.Kind == v.Kind {
				lmsQuestion = previous.Challenge.Question
			} else {
				var e error
				lmsQuestion, e = s.LMS.Question(r.Context(), u.ID, v.Kind, previous.LastQuestion)
				if e != nil {
					if errors.Is(e, ErrNoLMSQuestion) {
						return bad(409, "Chưa có quiz hoặc flashcard phù hợp trong khóa học LMS đã tham gia.")
					}
					return bad(503, "Chưa lấy được câu hỏi từ LMS. Hãy thử lại sau.")
				}
			}
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
			if s.LMS != nil {
				challenge, e = state.StartWithQuestion(1, v.Kind, g.Now, lmsQuestion)
			} else {
				challenge, e = state.Start(1, v.Kind, g.Now)
			}
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
