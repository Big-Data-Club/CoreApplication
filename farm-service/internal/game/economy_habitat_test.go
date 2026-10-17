package game

import (
	domain "bdc/farm-service/internal/gamedomain"
	"testing"
)

func TestWaterHomeRemainsHomeWhenOxygenRunsOut(t *testing.T) {
	habitat := gameEntity{ID: "pond1", Kind: "pond", Category: "STRUCTURE", X: 5, Y: 5, RT: domain.Runtime{Oxygen: 0}}
	frog := gameEntity{ID: "frog1", Kind: "frog", Category: "ANIMAL", X: 6, Y: 6}
	g := &gameTx{Entities: []gameEntity{habitat, frog}}
	if g.waterHomeAt(6, 6) == nil {
		t.Fatal("frog must remain in a physical pond with depleted oxygen")
	}
	g.setAquaticHabitatStatus(&g.Entities[1])
	if !g.Entities[1].Housed || g.Entities[1].HasOxygen || g.Entities[1].HabitatID != "pond1" {
		t.Fatalf("expected housed but oxygen depleted, got %+v", g.Entities[1])
	}
	if ok, _ := g.nearestHousing("frog", 6, 6); ok {
		t.Fatal("new frog placement must require oxygen")
	}
	g.Entities[0].RT.Oxygen = 70
	g.setAquaticHabitatStatus(&g.Entities[1])
	if !g.Entities[1].Housed || !g.Entities[1].HasOxygen || g.Entities[1].HabitatOxygen != 70 {
		t.Fatal("oxygen replenishment did not restore habitat")
	}
}

func TestWaterHomeRespectsFootprintAndBuildStatus(t *testing.T) {
	g := &gameTx{Entities: []gameEntity{
		{ID: "tank", Kind: "tank", Category: "STRUCTURE", X: 7, Y: 4, BuildLeft: 15, RT: domain.Runtime{Oxygen: 100}},
		{ID: "frog", Kind: "frog", Category: "ANIMAL", X: 8, Y: 5},
	}}
	if g.waterHomeAt(6, 5) != nil || g.waterHomeAt(7, 4) == nil {
		t.Fatal("habitat lookup must reject outside tiles and include the anchor")
	}
	g.setAquaticHabitatStatus(&g.Entities[1])
	if g.Entities[1].Housed || g.Entities[1].HabitatBuildLeft != 15 {
		t.Fatal("unbuilt tank must not be an active home")
	}
	g.Entities[0].BuildLeft = 0
	g.setAquaticHabitatStatus(&g.Entities[1])
	if !g.Entities[1].Housed || !g.Entities[1].HasOxygen {
		t.Fatal("completed tank was not recognized")
	}
}

func TestEightWaterSlotsAndCapacity(t *testing.T) {
	for _, kind := range []string{"tank", "pond"} {
		habitat := gameEntity{ID: "home", Kind: kind, Category: "STRUCTURE", X: 7, Y: 4, RT: domain.Runtime{Oxygen: 100}}
		g := &gameTx{Entities: []gameEntity{habitat}}
		// A water habitat is 4x2. ALL 8 coordinates, including the
		// structure anchor, must be usable (migration 006 allows overlap).
		for y := 4; y <= 5; y++ {
			for x := 7; x <= 10; x++ {
				if g.waterHomeAt(x, y) == nil {
					t.Fatalf("%s slot (%d,%d) not in water", kind, x, y)
				}
				if g.intersects(x, y, "fish", "") {
					t.Fatalf("%s slot (%d,%d) collides", kind, x, y)
				}
				if ok, _ := g.nearestHousing("fish", x, y); !ok {
					t.Fatalf("%s slot (%d,%d) rejected", kind, x, y)
				}
				g.Entities = append(g.Entities, gameEntity{ID: "fish-" + string(rune('0'+len(g.Entities))), Kind: "fish", Category: "ANIMAL", X: x, Y: y})
			}
		}
		for i := 1; i <= WaterHabitatCapacity; i++ {
			g.setAquaticHabitatStatus(&g.Entities[i])
			if !g.Entities[i].Housed {
				t.Fatalf("%s resident %d lost home at full capacity", kind, i)
			}
		}
		// An occupied tile cannot take a ninth animal, independent of capacity.
		if !g.intersects(7, 4, "frog", "") {
			t.Fatalf("%s lets two animals share a slot", kind)
		}
		// Simulate a ninth animal at a distinct coordinate within an already
		// full habitat (no physical room). Capacity guard must fail.
		if ok, _ := g.nearestHousing("frog", 7, 4); ok {
			t.Fatalf("%s exceeded capacity", kind)
		}
		// Moving an existing resident inside a full pond must not evict it.
		if ok, _ := g.nearestHousing("fish", 9, 5); !ok {
			t.Fatalf("%s resident cannot move", kind)
		}
	}
}
