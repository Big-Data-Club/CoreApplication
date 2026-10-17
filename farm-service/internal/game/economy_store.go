package game

import (
	domain "bdc/farm-service/internal/gamedomain"
	"github.com/jackc/pgx/v5"
	"math"
	"net/http"
	"time"
)

type life struct {
	LastTick               time.Time
	Hunger, Insects        int
	InsectSpawn, LastCatch time.Time
	Tutorial               int
	InsectSeeded           bool
}
type gameEntity struct {
	ID           string    `json:"id"`
	CreatedAt    time.Time `json:"-"`
	Kind         string    `json:"kind"`
	Category     string    `json:"category"`
	X            int       `json:"x"`
	Y            int       `json:"y"`
	Progress     float64   `json:"progress"`
	HungerPct    int       `json:"hungerPct"`
	Health       int       `json:"health"`
	Sick         bool      `json:"sick"`
	Ready        int       `json:"ready"`
	WaterPct     int       `json:"waterPct"`
	RegrowLeft   int       `json:"regrowLeft"`
	NeedsRewater bool      `json:"needsRewater"`
	Oxygen       int       `json:"oxygen"`
	OxygenLeft   int       `json:"oxygenLeft"`
	OnAquaponics bool      `json:"onAquaponics"`
	AquaActive   bool      `json:"aquaActive"`
	AquaOxygen   int       `json:"aquaOxygen"`
	RefundCoins  int       `json:"refundCoins"`
	BuildLeft    int       `json:"buildLeft"`
	Housed       bool      `json:"housed"`
	// Water-animal habitat and water quality are independent facts.
	// Low oxygen pauses production; it must not erase a physical home.
	HabitatID        string         `json:"habitatId,omitempty"`
	HabitatOxygen    int            `json:"habitatOxygen"`
	HabitatBuildLeft int            `json:"habitatBuildLeft"`
	HasOxygen        bool           `json:"hasOxygen"`
	Contained        bool           `json:"contained"`
	FlowerNearby     bool           `json:"flowerNearby"`
	Linked           bool           `json:"realLinked"`
	RT               domain.Runtime `json:"-"`
}
type gameTx struct {
	Farm      worldFarm
	Life      life
	Inventory map[string]int
	Entities  []gameEntity
	Insects   []wildInsect
	Now       time.Time
}

func secs(t time.Time, now time.Time) int {
	if t.IsZero() {
		return 0
	}
	return int(math.Max(0, now.Sub(t).Seconds()))
}
func near(x, y, a, b, r int) bool {
	return int(math.Abs(float64(x-a))) <= r && int(math.Abs(float64(y-b))) <= r
}
func (g *gameTx) readyStructure(kind string, x, y, r int) bool {
	for _, e := range g.Entities {
		if e.Kind == kind && e.BuildLeft == 0 && near(x, y, e.X, e.Y, r) {
			return true
		}
	}
	return false
}

// A 4x2 water habitat has eight usable cells, including its structure anchor.
// Migration 006 permits a water animal and its habitat structure to share the
// anchor coordinate while enforcing one animal per tile at the database level.
const WaterHabitatCapacity = 8

func (g *gameTx) nearestHousing(kind string, x, y int) (bool, string) {
	if kind == "bee" {
		for _, h := range g.Entities {
			if h.Kind != "hive" || h.BuildLeft > 0 || !near(x, y, h.X, h.Y, 2) {
				continue
			}
			occupied := 0
			alreadyHere := false
			for _, a := range g.Entities {
				if a.Kind == "bee" && near(a.X, a.Y, h.X, h.Y, 2) {
					occupied++
					if a.X == x && a.Y == y && a.Kind == kind {
						alreadyHere = true
					}
				}
			}
			if occupied < 2 || (alreadyHere && occupied <= 2) {
				return true, h.Kind
			}
		}
		return false, ""
	}
	if kind != "fish" && kind != "frog" {
		return false, ""
	}
	for _, h := range g.Entities {
		if (h.Kind != "tank" && h.Kind != "pond") || h.BuildLeft > 0 || h.RT.Oxygen <= domain.OxygenMinimum {
			continue
		}
		w, height := domain.Footprint(h.Kind)
		if x < h.X || x >= h.X+w || y < h.Y || y >= h.Y+height {
			continue
		}
		capacity := WaterHabitatCapacity
		occupied := 0
		alreadyHere := false
		for _, a := range g.Entities {
			if a.Category != "ANIMAL" || (a.Kind != "fish" && a.Kind != "frog") {
				continue
			}
			if a.X >= h.X && a.X < h.X+w && a.Y >= h.Y && a.Y < h.Y+height {
				occupied++
				if a.X == x && a.Y == y && a.Kind == kind {
					alreadyHere = true
				}
			}
		}
		if occupied < capacity || (alreadyHere && occupied <= capacity) {
			return true, h.Kind
		}
	}
	return false, ""
}

// Find a physical water habitat by footprint, regardless of its oxygen level
// or construction status. Keeping this distinct from the placement/capacity
// rules prevents an existing animal from suddenly becoming "homeless".
func (g *gameTx) waterHomeAt(x, y int) *gameEntity {
	for i := range g.Entities {
		h := &g.Entities[i]
		if h.Kind != "pond" && h.Kind != "tank" {
			continue
		}
		w, ht := domain.Footprint(h.Kind)
		if x >= h.X && x < h.X+w && y >= h.Y && y < h.Y+ht {
			return h
		}
	}
	return nil
}

func (g *gameTx) setAquaticHabitatStatus(animal *gameEntity) {
	if animal.Kind != "fish" && animal.Kind != "frog" {
		return
	}
	if h := g.waterHomeAt(animal.X, animal.Y); h != nil {
		animal.HabitatID = h.ID
		animal.HabitatOxygen = h.RT.Oxygen
		animal.HabitatBuildLeft = h.BuildLeft
		animal.Housed = h.BuildLeft == 0
		animal.HasOxygen = animal.Housed && h.RT.Oxygen > domain.OxygenMinimum
	}
}

// Used for production accounting even if oxygen has run out at the end of
// an offline interval. Current player actions still require usable oxygen.
func (g *gameTx) waterHabitatFor(x, y int) *gameEntity {
	h := g.waterHomeAt(x, y)
	if h != nil && h.BuildLeft == 0 {
		return h
	}
	return nil
}

// Split an offline interval at the exact time oxygen crosses 15%. Work can
// accrue before that instant, but never after; hunger still decays normally.
func advanceUntilOxygenEnds(kind string, rt domain.Runtime, now, until time.Time, floral bool) domain.Runtime {
	if until.After(rt.LastTick) {
		end := until
		if now.Before(end) {
			end = now
		}
		rt = domain.Advance(kind, rt, end, true, floral, domain.Goods[kind].Category == "CROP")
	}
	if now.After(rt.LastTick) {
		rt = domain.Advance(kind, rt, now, false, floral, false)
	}
	return rt
}
func (g *gameTx) flowerNear(x, y int) bool {
	for _, e := range g.Entities {
		if e.Kind == "flower" && e.RT.Ready > 0 && near(x, y, e.X, e.Y, 4) {
			return true
		}
	}
	return false
}

// A crop participates only if it occupies an actual planting slot in a finished
// 5x3 aquaponics deck. The anchor tile belongs to the structure's DB row.
func (g *gameTx) aquaFor(x, y int) *gameEntity {
	for i := range g.Entities {
		e := &g.Entities[i]
		if e.Kind != "aquaponics" || e.BuildLeft > 0 {
			continue
		}
		w, h := domain.Footprint(e.Kind)
		if x >= e.X && x < e.X+w && y >= e.Y && y < e.Y+h && (x != e.X || y != e.Y) {
			return e
		}
	}
	return nil
}
func (g *gameTx) aquaNear(x, y int) bool {
	a := g.aquaFor(x, y)
	return a != nil && a.RT.Oxygen > domain.OxygenMinimum
}
func (g *gameTx) entity(id string) *gameEntity {
	for i := range g.Entities {
		if g.Entities[i].ID == id {
			return &g.Entities[i]
		}
	}
	return nil
}
func (g *gameTx) inventoryQty(item string) int { return g.Inventory[item] }

// Each map coordinate has at most one anchor. A crop can overlay one of the
// 14 dedicated hydroponic slots, but cannot stand on the rack's anchor tile.
// The same overlap policy is used by placement and movement.
func (g *gameTx) intersects(x, y int, kind, except string) bool {
	for _, e := range g.Entities {
		if e.ID == except || !domain.Overlap(x, y, kind, e.X, e.Y, e.Kind) {
			continue
		}
		if e.Kind == "aquaponics" && e.BuildLeft == 0 && domain.Goods[kind].Category == "CROP" &&
			(x != e.X || y != e.Y) && x >= e.X && x < e.X+5 && y >= e.Y && y < e.Y+3 {
			continue
		}
		if (e.Kind == "pond" || e.Kind == "tank") && (kind == "fish" || kind == "frog") &&
			x >= e.X && x < e.X+4 && y >= e.Y && y < e.Y+2 {
			continue
		}
		return true
	}
	return false
}

// Start every game operation by locking its owning farm. This serializes coin, inventory,
// placement, production and reward writes and prevents double-harvest / double-spend.
func (s *Server) withGame(r *http.Request, u User, fn func(pgx.Tx, *gameTx) error) error {
	return s.tx(r.Context(), func(tx pgx.Tx) error {
		f, e := s.farmTx(r, tx, u.ID, true)
		if e != nil {
			return e
		}
		g := &gameTx{Farm: f, Inventory: map[string]int{}}
		if e = tx.QueryRow(r.Context(), "SELECT clock_timestamp()").Scan(&g.Now); e != nil {
			return e
		}
		tag, e := tx.Exec(r.Context(), `INSERT INTO farm_economy(farm_id) VALUES($1) ON CONFLICT DO NOTHING`, f.ID)
		if e != nil {
			return e
		}
		if tag.RowsAffected() == 1 {
			var count int
			if e = tx.QueryRow(r.Context(), `SELECT COUNT(*) FROM world_entities WHERE farm_id=$1`, f.ID).Scan(&count); e != nil {
				return e
			}
			if count == 0 {
				for _, v := range []struct {
					k, c string
					x, y int
				}{{"rice_crop", "CROP", 6, 5}, {"flower", "CROP", 8, 6}, {"chicken", "ANIMAL", 10, 5}} {
					if _, e = tx.Exec(r.Context(), `INSERT INTO world_entities(id,farm_id,category,kind,x,y) VALUES($1,$2,$3,$4,$5,$6)`, newID(), f.ID, v.c, v.k, v.x, v.y); e != nil {
						return e
					}
				}
			}
			// Exactly once for each farm, including seeded demo farms from the older version.
			for _, v := range []struct {
				k string
				n int
			}{{"paddy", 3}, {"rice", 2}, {"fish_feed", 2}, {"frog_feed", 2}, {"medicine", 1}, {"oxygen", 1}} {
				if _, e = tx.Exec(r.Context(), `INSERT INTO farm_inventory(farm_id,kind,quantity) VALUES($1,$2,$3) ON CONFLICT(farm_id,kind) DO NOTHING`, f.ID, v.k, v.n); e != nil {
					return e
				}
			}
		}
		e = tx.QueryRow(r.Context(), `SELECT last_tick,hunger_seconds,insects,insect_last_spawn,last_catch,tutorial_step,insect_seeded FROM farm_economy WHERE farm_id=$1 FOR UPDATE`, f.ID).Scan(&g.Life.LastTick, &g.Life.Hunger, &g.Life.Insects, &g.Life.InsectSpawn, &g.Life.LastCatch, &g.Life.Tutorial, &g.Life.InsectSeeded)
		if e != nil {
			return e
		}
		rows, e := tx.Query(r.Context(), `SELECT kind,quantity FROM farm_inventory WHERE farm_id=$1`, f.ID)
		if e != nil {
			return e
		}
		for rows.Next() {
			var k string
			var n int
			if e = rows.Scan(&k, &n); e != nil {
				break
			}
			g.Inventory[k] = n
		}
		if e == nil {
			e = rows.Err()
		}
		rows.Close()
		if e != nil {
			return e
		}
		_, e = tx.Exec(r.Context(), `INSERT INTO entity_runtime(entity_id,last_tick,hunger_seconds) SELECT id,$2,CASE WHEN category='ANIMAL' THEN 480 ELSE 0 END FROM world_entities WHERE farm_id=$1 ON CONFLICT DO NOTHING`, f.ID, g.Now)
		if e != nil {
			return e
		}
		entityRows, e := tx.Query(r.Context(), `SELECT we.id::text,we.kind,we.category,we.x,we.y,rt.last_tick,rt.work_seconds,rt.work_remainder,rt.hunger_seconds,rt.water_seconds,rt.health,rt.sick,rt.yield_ready,rt.oxygen,rt.oxygen_age_seconds,rt.starvation_seconds,rt.build_until,rt.regrow_until,we.created_at,FALSE FROM world_entities we JOIN entity_runtime rt ON rt.entity_id=we.id WHERE we.farm_id=$1 ORDER BY we.created_at, we.id FOR UPDATE OF we,rt`, f.ID)
		if e != nil {
			return e
		}
		for entityRows.Next() {
			var obj gameEntity
			var until *time.Time
			e = entityRows.Scan(&obj.ID, &obj.Kind, &obj.Category, &obj.X, &obj.Y, &obj.RT.LastTick, &obj.RT.Work, &obj.RT.Remainder, &obj.RT.Hunger, &obj.RT.Water, &obj.RT.Health, &obj.RT.Sick, &obj.RT.Ready, &obj.RT.Oxygen, &obj.RT.OxygenAge, &obj.RT.Starvation, &until, &obj.RT.RegrowUntil, &obj.CreatedAt, &obj.Linked)
			if e != nil {
				break
			}
			obj.RT.BuildUntil = until
			g.Entities = append(g.Entities, obj)
		}
		if e == nil {
			e = entityRows.Err()
		}
		entityRows.Close()
		if e != nil {
			return e
		}
		delta := secs(g.Life.LastTick, g.Now)
		g.Life.Hunger = domain.Clamp(g.Life.Hunger-delta, 0, domain.FarmerHungerCap)
		g.Life.LastTick = g.Now
		if _, e = tx.Exec(r.Context(), `UPDATE farm_economy SET last_tick=$2,hunger_seconds=$3 WHERE farm_id=$1`, f.ID, g.Now, g.Life.Hunger); e != nil {
			return e
		}

		fences := map[[2]int]bool{}
		for _, obj := range g.Entities {
			if obj.Kind == "fence" {
				fences[[2]int{obj.X, obj.Y}] = true
			}
		}
		// Preserve the oxygen deadline based on the pre-tick state. Animals and
		// hydro crops earn the time before a habitat depletes, even offline.
		oxygenUntil := map[string]time.Time{}
		var changedRuntime []*gameEntity
		for _, obj := range g.Entities {
			if domain.OxygenThresholdSeconds(obj.Kind) > 0 {
				oxygenUntil[obj.ID] = obj.RT.LastTick.Add(time.Duration(domain.OxygenLeftSeconds(obj.Kind, obj.RT)) * time.Second)
			}
		}
		// Structure states must be settled first, regardless of creation order.
		for i := range g.Entities {
			obj := &g.Entities[i]
			if obj.Category != "STRUCTURE" {
				continue
			}
			old := obj.RT
			if obj.RT.BuildUntil != nil {
				obj.BuildLeft = domain.Clamp(int(math.Ceil(obj.RT.BuildUntil.Sub(g.Now).Seconds())), 0, 86400)
			}
			if domain.OxygenThresholdSeconds(obj.Kind) > 0 {
				obj.RT = domain.DrainOxygen(obj.Kind, obj.RT, g.Now)
			} else {
				obj.RT.LastTick = g.Now
			}
			if obj.RT != old {
				changedRuntime = append(changedRuntime, obj)
			}
		}
		for i := range g.Entities {
			obj := &g.Entities[i]
			if obj.Category != "CROP" {
				continue
			}
			old := obj.RT
			if hydro := g.aquaFor(obj.X, obj.Y); hydro != nil {
				obj.RT = advanceUntilOxygenEnds(obj.Kind, obj.RT, g.Now, oxygenUntil[hydro.ID], false)
			} else {
				obj.RT = domain.Advance(obj.Kind, obj.RT, g.Now, false, false, false)
			}
			if obj.RT != old {
				changedRuntime = append(changedRuntime, obj)
			}
		}
		for i := range g.Entities {
			obj := &g.Entities[i]
			if obj.Category != "ANIMAL" {
				continue
			}
			old := obj.RT
			floral := g.flowerNear(obj.X, obj.Y)
			if obj.Kind == "fish" || obj.Kind == "frog" {
				if habitat := g.waterHabitatFor(obj.X, obj.Y); habitat != nil {
					obj.RT = advanceUntilOxygenEnds(obj.Kind, obj.RT, g.Now, oxygenUntil[habitat.ID], floral)
				} else {
					obj.RT = domain.Advance(obj.Kind, obj.RT, g.Now, false, floral, false)
				}
			} else {
				housed, _ := g.nearestHousing(obj.Kind, obj.X, obj.Y)
				obj.RT = domain.Advance(obj.Kind, obj.RT, g.Now, housed, floral, false)
			}
			if obj.RT != old {
				changedRuntime = append(changedRuntime, obj)
			}
		}
		if e = updateRuntimes(r, tx, changedRuntime); e != nil {
			return e
		}
		for i := range g.Entities {
			obj := &g.Entities[i]
			obj.Progress = domain.Progress(obj.Kind, obj.RT)
			obj.Health = obj.RT.Health
			obj.Sick = obj.RT.Sick
			obj.Ready = obj.RT.Ready
			obj.Oxygen = obj.RT.Oxygen
			obj.OxygenLeft = domain.OxygenLeftSeconds(obj.Kind, obj.RT)
			obj.RefundCoins = domain.RemovalRefund(obj.Kind, secs(obj.CreatedAt, g.Now))
			obj.HungerPct = domain.Clamp(obj.RT.Hunger*100/domain.AnimalHungerCap, 0, 100)
			obj.WaterPct = domain.Clamp(obj.RT.Water*100/domain.CropWaterCap, 0, 100)
			if obj.Category == "CROP" {
				aqua := g.aquaFor(obj.X, obj.Y)
				obj.OnAquaponics = aqua != nil
				obj.AquaActive = aqua != nil && aqua.RT.Oxygen > domain.OxygenMinimum
				if aqua != nil {
					obj.AquaOxygen = aqua.RT.Oxygen
				}
				obj.RegrowLeft = domain.CropRegrowLeft(obj.RT, g.Now)
				obj.NeedsRewater = obj.RT.RegrowUntil != nil && !obj.OnAquaponics
			}
			if obj.Category == "ANIMAL" {
				if obj.Kind == "fish" || obj.Kind == "frog" {
					g.setAquaticHabitatStatus(obj)
				} else {
					obj.Housed, _ = g.nearestHousing(obj.Kind, obj.X, obj.Y)
				}
				obj.FlowerNearby = g.flowerNear(obj.X, obj.Y)
			}
			if obj.Kind == "chicken" {
				obj.Contained = domain.Enclosed(obj.X, obj.Y, fences)
			}
		}
		if e = s.syncWildInsects(r, tx, g); e != nil {
			return e
		}
		return fn(tx, g)
	})
}

const updateRuntimeSQL = `UPDATE entity_runtime SET last_tick=$2,work_seconds=$3,hunger_seconds=$4,water_seconds=$5,health=$6,sick=$7,yield_ready=$8,oxygen=$9,build_until=$10,oxygen_age_seconds=$11,starvation_seconds=$12,work_remainder=$13,regrow_until=$14 WHERE entity_id=$1`

func updateRuntimes(r *http.Request, tx pgx.Tx, entities []*gameEntity) error {
	if len(entities) == 0 {
		return nil
	}
	batch := &pgx.Batch{}
	for _, e := range entities {
		batch.Queue(updateRuntimeSQL, e.ID, e.RT.LastTick, e.RT.Work, e.RT.Hunger, e.RT.Water, e.RT.Health, e.RT.Sick, e.RT.Ready, e.RT.Oxygen, e.RT.BuildUntil, e.RT.OxygenAge, e.RT.Starvation, e.RT.Remainder, e.RT.RegrowUntil)
	}
	results := tx.SendBatch(r.Context(), batch)
	for range entities {
		if _, err := results.Exec(); err != nil {
			_ = results.Close()
			return err
		}
	}
	return results.Close()
}

// One-off runtime changes during an action do not need a batch.
func updateRuntime(r *http.Request, tx pgx.Tx, e *gameEntity) error {
	_, err := tx.Exec(r.Context(), updateRuntimeSQL, e.ID, e.RT.LastTick, e.RT.Work, e.RT.Hunger, e.RT.Water, e.RT.Health, e.RT.Sick, e.RT.Ready, e.RT.Oxygen, e.RT.BuildUntil, e.RT.OxygenAge, e.RT.Starvation, e.RT.Remainder, e.RT.RegrowUntil)
	return err
}

// Never INSERT a negative quantity: PostgreSQL validates CHECK(quantity>=0)
// before ON CONFLICT, even if the final result would be nonnegative.
// All changes occur inside withGame, which serializes updates by locking the farm.
func (s *Server) gameInv(r *http.Request, tx pgx.Tx, g *gameTx, kind string, delta int) error {
	before := g.Inventory[kind]
	if before+delta < 0 {
		return bad(409, "Kho không đủ %s", domain.Labels[kind])
	}
	if delta == 0 {
		return nil
	}
	if delta > 0 {
		_, err := tx.Exec(r.Context(), `INSERT INTO farm_inventory(farm_id,kind,quantity) VALUES($1,$2,$3)
            ON CONFLICT(farm_id,kind) DO UPDATE SET quantity=farm_inventory.quantity+EXCLUDED.quantity`, g.Farm.ID, kind, delta)
		if err != nil {
			return err
		}
	} else {
		tag, err := tx.Exec(r.Context(), `UPDATE farm_inventory SET quantity=quantity+$3
            WHERE farm_id=$1 AND kind=$2 AND quantity >= $4`, g.Farm.ID, kind, delta, -delta)
		if err != nil {
			return err
		}
		if tag.RowsAffected() != 1 {
			return bad(409, "Kho không đủ %s", domain.Labels[kind])
		}
	}
	g.Inventory[kind] = before + delta
	return nil
}
func (s *Server) gameCoins(r *http.Request, tx pgx.Tx, g *gameTx, coins, xp int, typ, kind string, qty int) error {
	if g.Farm.Coins+coins < 0 {
		return bad(409, "Bạn cần thêm %d Xu Lá", -(g.Farm.Coins + coins))
	}
	_, e := tx.Exec(r.Context(), `UPDATE virtual_farms SET coins=coins+$2,xp=xp+$3 WHERE id=$1`, g.Farm.ID, coins, xp)
	if e != nil {
		return e
	}
	_, e = tx.Exec(r.Context(), `INSERT INTO economy_ledger(id,farm_id,event_type,kind,quantity,coins_delta) VALUES($1,$2,$3,$4,$5,$6)`, newID(), g.Farm.ID, typ, kind, qty, coins)
	if e != nil {
		return e
	}
	g.Farm.Coins += coins
	g.Farm.XP += xp
	g.Farm.Level = domain.Level(g.Farm.XP)
	return nil
}
func activeWorker(g *gameTx) error {
	if !domain.FarmerCanWork(g.Life.Hunger) {
		return bad(409, "Nông dân cần ăn cơm để làm tiếp! Xay thóc, nấu cơm rồi ăn.")
	}
	return nil
}
func goodTile(x, y int, kind string) bool {
	w, h := domain.Footprint(kind)
	for dy := 0; dy < h; dy++ {
		for dx := 0; dx < w; dx++ {
			if !domain.ValidTile(x+dx, y+dy) {
				return false
			}
		}
	}
	return true
}

// This learning game never reserves assets for real-world farms.
func checkReservedAnimal(_ *http.Request, _ pgx.Tx, _ *gameEntity) error { return nil }
