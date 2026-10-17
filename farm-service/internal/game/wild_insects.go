package game

import (
	"math/rand"
	"net/http"
	"time"

	domain "bdc/farm-service/internal/gamedomain"
	"github.com/jackc/pgx/v5"
)

// Wild insects are separate from inventory: they have stable IDs and world
// coordinates. Catching turns a single living insect into exactly one feed item.
type wildInsect struct {
	ID      string `json:"id"`
	Species string `json:"species"`
	X       int    `json:"x"`
	Y       int    `json:"y"`
}

const (
	maxWildInsects = 4
	spawnInterval  = 75 * time.Second
	insectLifetime = 12 * time.Minute
	catchWait      = 8 * time.Second
)

var wildSpecies = []string{"ladybug", "grasshopper", "grasshopper", "butterfly", "dragonfly"}
var wildNames = map[string]string{"ladybug": "bọ rùa", "grasshopper": "châu chấu", "butterfly": "bướm", "dragonfly": "chuồn chuồn"}

// Under the withGame farm row lock, updates/spawns/catches cannot race or
// duplicate. Candidates avoid houses, paths, decorations, ponds and animals.
func insectCandidates(g *gameTx) [][2]int {
	weighted := make([][2]int, 0, domain.Width*domain.Height)
	for y := 1; y < domain.Height-1; y++ {
		for x := 1; x < domain.Width-1; x++ {
			if !domain.ValidTile(x, y) || (x == 4 && y > 2 && y < 12) || (y == 9 && x >= 4 && x <= 15) {
				continue
			}
			blocked := false
			for _, o := range g.Entities {
				if domain.Overlap(x, y, "insect", o.X, o.Y, o.Kind) {
					blocked = true
					break
				}
			}
			for _, bug := range g.Insects {
				if bug.X == x && bug.Y == y {
					blocked = true
					break
				}
			}
			if blocked {
				continue
			}
			weighted = append(weighted, [2]int{x, y})
			// Favor plants and flowers, but preserve an element of surprise.
			for _, o := range g.Entities {
				if o.Category == "CROP" && near(x, y, o.X, o.Y, 2) {
					weighted = append(weighted, [2]int{x, y}, [2]int{x, y})
					break
				}
			}
		}
	}
	return weighted
}

func (s *Server) syncWildInsects(r *http.Request, tx pgx.Tx, g *gameTx) error {
	ctx := r.Context()
	if _, e := tx.Exec(ctx, `DELETE FROM farm_wild_insects WHERE farm_id=$1 AND expires_at <= $2`, g.Farm.ID, g.Now); e != nil {
		return e
	}
	rows, e := tx.Query(ctx, `SELECT id::text,species,x,y FROM farm_wild_insects WHERE farm_id=$1 ORDER BY spawned_at,id`, g.Farm.ID)
	if e != nil {
		return e
	}
	g.Insects = []wildInsect{}
	for rows.Next() {
		var bug wildInsect
		if e = rows.Scan(&bug.ID, &bug.Species, &bug.X, &bug.Y); e != nil {
			break
		}
		g.Insects = append(g.Insects, bug)
	}
	if e == nil {
		e = rows.Err()
	}
	rows.Close()
	if e != nil {
		return e
	}
	birthCount := 0
	if !g.Life.InsectSeeded {
		// Two bugs on the very first visit, never a free refill on refresh.
		birthCount = 2
		g.Life.InsectSpawn = g.Now
		g.Life.InsectSeeded = true
	} else if elapsed := g.Now.Sub(g.Life.InsectSpawn); elapsed >= spawnInterval {
		// Cap catch-up and never repeatedly resimulate after reconnect.
		birthCount = int(elapsed / spawnInterval)
		if birthCount > maxWildInsects {
			birthCount = maxWildInsects
		}
		g.Life.InsectSpawn = g.Now
	}
	if birthCount > maxWildInsects-len(g.Insects) {
		birthCount = maxWildInsects - len(g.Insects)
	}
	for i := 0; i < birthCount; i++ {
		places := insectCandidates(g)
		if len(places) == 0 {
			break
		}
		pos := places[rand.Intn(len(places))]
		species := wildSpecies[rand.Intn(len(wildSpecies))]
		bug := wildInsect{ID: newID(), Species: species, X: pos[0], Y: pos[1]}
		if _, e = tx.Exec(ctx, `INSERT INTO farm_wild_insects(id,farm_id,species,x,y,spawned_at,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7)`, bug.ID, g.Farm.ID, bug.Species, bug.X, bug.Y, g.Now, g.Now.Add(insectLifetime)); e != nil {
			return e
		}
		g.Insects = append(g.Insects, bug)
	}
	g.Life.Insects = len(g.Insects)
	_, e = tx.Exec(ctx, `UPDATE farm_economy SET insects=$2,insect_last_spawn=$3,insect_seeded=$4 WHERE farm_id=$1`, g.Farm.ID, g.Life.Insects, g.Life.InsectSpawn, g.Life.InsectSeeded)
	return e
}

// Insects flee if their grass tile is turned into a new structure or crop.
// This is a despawn (never a catch), so it yields no inventory or XP.
func (s *Server) evictWildInsects(r *http.Request, tx pgx.Tx, g *gameTx, x, y int, kind string) error {
	width, height := domain.Footprint(kind)
	survivors := make([]wildInsect, 0, len(g.Insects))
	for _, bug := range g.Insects {
		if bug.X >= x && bug.X < x+width && bug.Y >= y && bug.Y < y+height {
			if _, e := tx.Exec(r.Context(), `DELETE FROM farm_wild_insects WHERE farm_id=$1 AND id=$2`, g.Farm.ID, bug.ID); e != nil {
				return e
			}
			continue
		}
		survivors = append(survivors, bug)
	}
	if len(survivors) == len(g.Insects) {
		return nil
	}
	g.Insects = survivors
	g.Life.Insects = len(survivors)
	_, e := tx.Exec(r.Context(), `UPDATE farm_economy SET insects=$2 WHERE farm_id=$1`, g.Farm.ID, g.Life.Insects)
	return e
}
