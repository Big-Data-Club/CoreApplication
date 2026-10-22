package game

import (
	domain "bdc/farm-service/internal/gamedomain"
	"testing"
	"time"
)

func TestLegacyFarmGetsFreshCareCycleWithoutLosingProgress(t *testing.T) {
	now := time.Date(2026, 10, 23, 12, 0, 0, 0, time.UTC)
	g := &gameTx{Now: now, Entities: []gameEntity{
		{Category: "ANIMAL", Kind: "chicken", RT: domain.Runtime{Hunger: 0, Starvation: 90000, Health: 30, Sick: true, Ready: 1}},
		{Category: "CROP", Kind: "rice_crop", RT: domain.Runtime{Water: 0, Work: 80}},
		{Category: "STRUCTURE", Kind: "pond", RT: domain.Runtime{Oxygen: 10, OxygenAge: 2700}},
	}}
	changed := upgradeCareTimers(g)
	if len(changed) != 3 || g.Life.Hunger != domain.FarmerHungerCap || !g.Life.LastTick.Equal(now) {
		t.Fatalf("farmer was not refreshed: %+v", g.Life)
	}
	chicken := g.Entities[0].RT
	if chicken.Hunger != domain.AnimalHungerCap || chicken.Starvation != 0 || chicken.Health != 100 || chicken.Sick || chicken.Ready != 1 {
		t.Fatalf("animal care upgrade changed progress: %+v", chicken)
	}
	if g.Entities[1].RT.Water != domain.CropWaterCap || g.Entities[1].RT.Work != 80 {
		t.Fatalf("crop care upgrade changed progress: %+v", g.Entities[1].RT)
	}
	if g.Entities[2].RT.Oxygen != 100 || g.Entities[2].RT.OxygenAge != 0 {
		t.Fatalf("habitat was not refilled: %+v", g.Entities[2].RT)
	}
	for _, obj := range g.Entities {
		if !obj.RT.LastTick.Equal(now) {
			t.Fatal("old offline time would be charged after the upgrade")
		}
	}
}
