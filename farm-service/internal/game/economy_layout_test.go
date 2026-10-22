package game

import (
	domain "bdc/farm-service/internal/gamedomain"
	"testing"
	"time"
)

func TestAquaponicsSlotAndCollision(t *testing.T) {
	g := &gameTx{Entities: []gameEntity{{ID: "rack", Category: "STRUCTURE", Kind: "aquaponics", X: 7, Y: 7, BuildLeft: 0}}}
	if g.intersects(8, 8, "mustard", "") {
		t.Fatal("crop should plant on rack")
	}
	if !g.intersects(7, 7, "mustard", "") {
		t.Fatal("rack anchor must be reserved")
	}
	if !g.intersects(8, 8, "chicken", "") {
		t.Fatal("animal cannot be inside rack")
	}
	if !g.intersects(11, 9, "pond", "") {
		t.Fatal("overlapping habitat not blocked")
	}
	if !g.intersects(8, 8, "tank", "") {
		t.Fatal("overlapping structure not blocked")
	}
	if g.intersects(12, 7, "mustard", "") {
		t.Fatal("outside rack should be free")
	}
	g.Entities[0].BuildLeft = 5
	if !g.intersects(8, 8, "mustard", "") {
		t.Fatal("must not plant before rack built")
	}
}
func TestProductionCreditsOnlyOxygenAvailable(t *testing.T) {
	t0 := time.Date(2026, 10, 14, 7, 0, 0, 0, time.UTC)
	animal := domain.Runtime{LastTick: t0, Hunger: domain.AnimalHungerCap, Health: 100}
	actual := advanceUntilOxygenEnds("fish", animal, t0.Add(10*time.Minute), t0.Add(5*time.Minute), false)
	if actual.Work != 300 || actual.Hunger != domain.AnimalHungerCap-600 {
		t.Fatalf("fish credited time past oxygen expiry: %+v", actual)
	}
	crop := domain.Runtime{LastTick: t0, Water: 0}
	hydro := advanceUntilOxygenEnds("water_spinach", crop, t0.Add(3*time.Minute), t0.Add(1*time.Minute), false)
	if hydro.Work != 72 {
		t.Fatalf("hydro should only receive first minute of 120%% acceleration: %+v", hydro)
	}
	again := advanceUntilOxygenEnds("water_spinach", hydro, t0.Add(3*time.Minute), t0.Add(1*time.Minute), false)
	if again.Work != hydro.Work {
		t.Fatal("polling twice changed production")
	}
}
