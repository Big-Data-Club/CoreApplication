package game

import (
	domain "bdc/farm-service/internal/gamedomain"
	"math"
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
