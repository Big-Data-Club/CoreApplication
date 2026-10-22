package gamedomain

import (
	"testing"
	"time"
)

func TestAnimalHungerPausesProduction(t *testing.T) {
	now := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
	r := Runtime{LastTick: now, Hunger: 300, Health: 100}
	r = Advance("chicken", r, now.Add(500*time.Second), true, true, false)
	if r.Work != 300 || r.Hunger != 0 || r.Ready != 0 {
		t.Fatalf("pause %+v", r)
	}
	r.Hunger = 480
	r = Advance("chicken", r, now.Add(600*time.Second), true, true, false)
	if r.Ready != 1 || r.Work != 40 {
		t.Fatalf("resume %+v", r)
	}
}
func TestFlowerNeedsWater(t *testing.T) {
	now := time.Now()
	r := Runtime{LastTick: now, Water: 0}
	r = Advance("flower", r, now.Add(200*time.Second), false, false, false)
	if r.Ready != 0 || r.Work != 0 {
		t.Fatal(r)
	}
	r.Water = 180
	r = Advance("flower", r, now.Add(300*time.Second), false, false, false)
	if r.Ready != 1 {
		t.Fatal(r)
	}
}
func TestEnclosure(t *testing.T) {
	f := map[[2]int]bool{}
	for x := 5; x <= 8; x++ {
		f[[2]int{x, 4}] = true
		f[[2]int{x, 7}] = true
	}
	for y := 4; y <= 7; y++ {
		f[[2]int{5, y}] = true
		f[[2]int{8, y}] = true
	}
	if !Enclosed(6, 6, f) {
		t.Fatal("closed ring")
	}
	if Enclosed(10, 6, f) {
		t.Fatal("free roam")
	}
	delete(f, [2]int{6, 4})
	if Enclosed(6, 6, f) {
		t.Fatal("open fence")
	}
}
func TestOverlap(t *testing.T) {
	if !Overlap(5, 5, "pond", 6, 5, "tank") || Overlap(5, 5, "pond", 7, 7, "tank") {
		t.Fatal("footprint")
	}
}

func TestStarvationIndependentOfPolling(t *testing.T) {
	now := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
	first := Runtime{LastTick: now, Hunger: 0, Health: 100}
	fast := first
	for i := 1; i <= 720; i++ {
		fast = Advance("chicken", fast, now.Add(time.Duration(i*10)*time.Second), true, true, false)
	}
	slow := Advance("chicken", first, now.Add(7200*time.Second), true, true, false)
	if fast.Health != slow.Health || fast.Starvation != slow.Starvation {
		t.Fatalf("different results %+v %+v", fast, slow)
	}
}

func TestAquaponicsChunkIndependent(t *testing.T) {
	now := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
	r := Runtime{LastTick: now}
	for i := 1; i <= 60; i++ {
		r = Advance("water_spinach", r, now.Add(time.Duration(i)*time.Second), false, false, true)
	}
	whole := Advance("water_spinach", Runtime{LastTick: now}, now.Add(60*time.Second), false, false, true)
	if r.Work != whole.Work || r.Remainder != whole.Remainder || r.Work != 72 {
		t.Fatalf("aquaponic progress %v vs %v", r, whole)
	}
}

func TestWaterAnimalsRequireHousing(t *testing.T) {
	start := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
	r := Runtime{LastTick: start, Hunger: 480, Health: 100}
	without := Advance("frog", r, start.Add(360*time.Second), false, false, false)
	if without.Work != 0 || without.Ready != 0 {
		t.Fatalf("frog grew without water housing %+v", without)
	}
	with := Advance("frog", r, start.Add(360*time.Second), true, false, false)
	if with.Work != 360 || with.Ready != 0 {
		t.Fatalf("frog with housing did not progress %+v", with)
	}
}
func TestBeesRequireBloom(t *testing.T) {
	start := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
	r := Runtime{LastTick: start, Hunger: 480, Health: 100}
	without := Advance("bee", r, start.Add(330*time.Second), true, false, false)
	if without.Ready != 0 || without.Work != 0 {
		t.Fatalf("bee made honey without flowers %+v", without)
	}
	with := Advance("bee", r, start.Add(330*time.Second), true, true, false)
	if with.Ready != 1 {
		t.Fatalf("bee missed honey cycle %+v", with)
	}
}
func TestFeedingDoesNotSkipProduction(t *testing.T) {
	start := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
	r := Runtime{LastTick: start, Hunger: 120, Health: 100, Work: 140}
	after := Advance("chicken", r, start.Add(300*time.Second), true, true, false)
	if after.Work != 260 || after.Ready != 0 || after.Hunger != 0 {
		t.Fatalf("hunger did not pause timer %+v", after)
	}
	// FEED replenishes the hungry meter but never manipulates the production work.
	after.Hunger = 480
	again := Advance("chicken", after, start.Add(400*time.Second), true, true, false)
	if again.Work != 0 || again.Ready != 1 {
		t.Fatalf("resume should require 100 more healthy fed seconds %+v", again)
	}
}

func TestCareTimersAllowTwelveHoursBeforeInterruption(t *testing.T) {
	if FarmerHungerCap != 12*60*60 || AnimalHungerCap != FarmerHungerCap || CropWaterCap != FarmerHungerCap {
		t.Fatal("care timers must use the same 12-hour cycle")
	}
	start := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
	animal := Runtime{LastTick: start, Hunger: AnimalHungerCap, Health: 100}
	before := Advance("chicken", animal, start.Add(12*time.Hour-time.Second), true, true, false)
	if before.Hunger != 1 || before.Sick {
		t.Fatalf("animal stopped too early: %+v", before)
	}
	atLimit := Advance("chicken", before, start.Add(12*time.Hour), true, true, false)
	if atLimit.Hunger != 0 || atLimit.Health != 100 {
		t.Fatalf("animal hunger deadline incorrect: %+v", atLimit)
	}
	grace := Advance("chicken", atLimit, start.Add(24*time.Hour), true, true, false)
	if grace.Health != 100 || grace.Sick {
		t.Fatalf("starvation grace ended too early: %+v", grace)
	}
	later := Advance("chicken", grace, start.Add(25*time.Hour), true, true, false)
	if later.Health != 97 || later.Sick {
		t.Fatalf("health should decline gradually after grace: %+v", later)
	}
}
func TestPondFootprintAndBoundaries(t *testing.T) {
	if !Overlap(18, 12, "pond", 19, 13, "fish") {
		t.Fatal("pond must cover its water footprint")
	}
	if ValidTile(-1, 0) || ValidTile(Width, 0) || ValidTile(2, 2) {
		t.Fatal("out-of-bounds and house tiles cannot be built on")
	}
}

func TestWaterHabitatsFourByTwo(t *testing.T) {
	for _, kind := range []string{"pond", "tank"} {
		w, h := Footprint(kind)
		if w != 4 || h != 2 {
			t.Fatalf("%s must be 4x2, got %dx%d", kind, w, h)
		}
		if !Overlap(8, 7, kind, 11, 8, "fish") {
			t.Fatalf("%s rightmost water cell must overlap", kind)
		}
		if Overlap(8, 7, kind, 12, 8, "fish") {
			t.Fatalf("%s outside cell must not overlap", kind)
		}
		if Overlap(8, 7, kind, 8, 9, "fish") {
			t.Fatalf("%s outside bottom must not overlap", kind)
		}
	}
}

// A crop keeps its remaining moisture after harvest, but cannot grow once dry.
func TestHarvestedCropRetainsMoistureUntilDry(t *testing.T) {
	now := time.Date(2026, 10, 14, 12, 0, 0, 0, time.UTC)
	initial := Runtime{LastTick: now.Add(-125 * time.Second), Water: 20, Work: 125, Remainder: 7, Ready: 1}
	harvested := HarvestCrop(initial, now)
	if harvested.Ready != 0 || harvested.Work != 0 || harvested.Water != 20 || harvested.Remainder != 0 || harvested.RegrowUntil == nil {
		t.Fatalf("harvest reset is incomplete: %+v", harvested)
	}
	if CropRegrowLeft(harvested, now) != 40 || CanWaterCrop(harvested, now.Add(39*time.Second)) {
		t.Fatalf("40 seconds of rest required: %+v", harvested)
	}
	// Poll in the middle: nothing can grow, even near aquaponics.
	paused := Advance("mustard", harvested, now.Add(25*time.Second), false, false, false)
	if paused.Work != 0 || paused.Ready != 0 || paused.RegrowUntil == nil {
		t.Fatalf("crop advanced in rest: %+v", paused)
	}
	// A small remaining water supply runs out while the player is away.
	paused = Advance("mustard", paused, now.Add(5*time.Minute), false, false, false)
	if paused.Work != 0 || paused.Water != 0 || !CanWaterCrop(paused, now.Add(5*time.Minute)) {
		t.Fatalf("crop grew without rewatering: %+v", paused)
	}
	// No retroactive growth after watering at minute five.
	resumed := WaterCrop(paused, now.Add(5*time.Minute))
	if resumed.RegrowUntil != nil || resumed.Work != 0 || resumed.Water != CropWaterCap {
		t.Fatalf("watering failed: %+v", resumed)
	}
	resumed = Advance("mustard", resumed, now.Add(5*time.Minute+10*time.Second), false, false, false)
	if resumed.Work != 10 || resumed.Ready != 0 {
		t.Fatalf("growth credited incorrect amount: %+v", resumed)
	}
}

func TestCropCooldownRemainsAccurateWithoutPolling(t *testing.T) {
	now := time.Date(2026, 10, 14, 12, 0, 0, 0, time.UTC)
	rt := HarvestCrop(Runtime{LastTick: now, Ready: 1, Work: 120, Water: CropWaterCap}, now)
	rt = Advance("rice_crop", rt, now.Add(39*time.Second), false, false, false)
	if CropRegrowLeft(rt, now.Add(39*time.Second)) != 1 || CanWaterCrop(rt, now.Add(39*time.Second)) {
		t.Fatalf("premature watering: %+v", rt)
	}
	rt = Advance("rice_crop", rt, now.Add(40*time.Second), false, false, false)
	if CropRegrowLeft(rt, now.Add(40*time.Second)) != 0 || rt.RegrowUntil != nil || rt.Water != CropWaterCap-40 {
		t.Fatalf("not released after 40 seconds: %+v", rt)
	}
	rt = Advance("rice_crop", rt, now.Add(2*time.Minute+40*time.Second), false, false, false)
	if rt.Ready != 1 {
		t.Fatalf("moist crop did not start the next season automatically: %+v", rt)
	}
}

func TestDryHarvestedCropWaitsForWaterAfterFortySeconds(t *testing.T) {
	start := time.Date(2026, 10, 14, 3, 0, 0, 0, time.UTC)
	ready := Runtime{LastTick: start, Work: Goods["rice_crop"].Seconds, Water: 0, Ready: 1}
	after := HarvestCrop(ready, start)
	if after.Ready != 0 || after.Work != 0 || after.Water != 0 || after.RegrowUntil == nil {
		t.Fatalf("harvest did not reset plant runtime: %+v", after)
	}
	if left := CropRegrowLeft(after, start.Add(39*time.Second)); left != 1 {
		t.Fatalf("expected one second of cooldown, got %d", left)
	}
	if CanWaterCrop(after, start.Add(39*time.Second)) || !CanWaterCrop(after, start.Add(40*time.Second)) {
		t.Fatal("watering guard ignored the 40-second cooldown")
	}
	// Even after cooldown, the crop cannot accumulate growth before its next watering.
	dormant := Advance("rice_crop", after, start.Add(10*time.Minute), true, true, false)
	if dormant.Work != 0 || dormant.Ready != 0 {
		t.Fatalf("dry crop grew without rewatering: %+v", dormant)
	}
	// Watering starts a new cycle without crediting the dry interval.
	dormant = WaterCrop(dormant, start.Add(10*time.Minute))
	next := Advance("rice_crop", dormant, start.Add(11*time.Minute), false, false, false)
	if next.Work != 60 || next.Ready != 0 {
		t.Fatalf("rewatered crop should restart its growth cycle: %+v", next)
	}
}

// Aquaponics occupies 15 cells, one reserved for its structure anchor.
func TestAquaponicsFootprint(t *testing.T) {
	w, h := Footprint("aquaponics")
	if w != 5 || h != 3 {
		t.Fatalf("wrong rack size: %dx%d", w, h)
	}
	if !Overlap(4, 4, "aquaponics", 8, 6, "water_spinach") {
		t.Fatal("last hydro cell ignored")
	}
	if Overlap(4, 4, "aquaponics", 9, 6, "water_spinach") {
		t.Fatal("extra hydro cell")
	}
}
func TestOxygenDecayAndRefillTiming(t *testing.T) {
	now := time.Date(2026, 10, 14, 11, 0, 0, 0, time.UTC)
	for _, tc := range []struct {
		kind     string
		duration int
	}{
		{"pond", CareCycleSeconds}, {"tank", CareCycleSeconds}, {"aquaponics", CareCycleSeconds},
	} {
		if got := OxygenThresholdSeconds(tc.kind); got != tc.duration {
			t.Fatalf("%s duration got %d expected %d", tc.kind, got, tc.duration)
		}
		base := Runtime{LastTick: now, Oxygen: 100}
		if left := OxygenLeftSeconds(tc.kind, base); left != tc.duration {
			t.Fatalf("%s initial oxygen %d", tc.kind, left)
		}
		// Multiple short polls and one long offline interval must agree.
		polled := base
		for tick := 60; tick <= tc.duration; tick += 60 {
			polled = DrainOxygen(tc.kind, polled, now.Add(time.Duration(tick)*time.Second))
		}
		offline := DrainOxygen(tc.kind, base, now.Add(time.Duration(tc.duration)*time.Second))
		if polled.Oxygen != 15 || offline.Oxygen != 15 || OxygenLeftSeconds(tc.kind, offline) != 0 {
			t.Fatalf("%s threshold wrong, polled=%+v offline=%+v", tc.kind, polled, offline)
		}
		before := DrainOxygen(tc.kind, base, now.Add(time.Duration(tc.duration-1)*time.Second))
		if before.Oxygen <= OxygenMinimum || OxygenLeftSeconds(tc.kind, before) != 1 {
			t.Fatalf("%s stopped early: %+v", tc.kind, before)
		}
		midway := DrainOxygen(tc.kind, base, now.Add(time.Duration(tc.duration/2)*time.Second))
		if midway.Oxygen <= OxygenMinimum || midway.Oxygen >= 100 || OxygenLeftSeconds(tc.kind, midway) != tc.duration/2 {
			t.Fatalf("%s lost timing in middle: %+v", tc.kind, midway)
		}
		unchanged := DrainOxygen(tc.kind, midway, midway.LastTick)
		if unchanged.Oxygen != midway.Oxygen || unchanged.OxygenAge != midway.OxygenAge {
			t.Fatal("same timestamp must never consume oxygen")
		}
		// Refill never credits previous downtime: only the remaining points count.
		midway = RefillOxygen(midway)
		remaining := OxygenLeftSeconds(tc.kind, midway)
		if remaining != tc.duration {
			t.Fatalf("%s bad refill duration %d", tc.kind, remaining)
		}
		after := DrainOxygen(tc.kind, midway, midway.LastTick.Add(time.Duration(remaining)*time.Second))
		if after.Oxygen != OxygenMinimum {
			t.Fatalf("%s bad refill threshold %+v", tc.kind, after)
		}
	}
}

func TestAutoRegrowOnHydroponicsOnlyWithOxygen(t *testing.T) {
	now := time.Date(2026, 10, 14, 12, 0, 0, 0, time.UTC)
	after := HarvestCrop(Runtime{LastTick: now, Ready: 1, Work: 125}, now)
	paused := Advance("mustard", after, now.Add(4*time.Minute), false, false, false)
	if paused.Work != 0 || paused.RegrowUntil == nil {
		t.Fatal("crop grew without oxygen")
	}
	resumed := Advance("mustard", paused, now.Add(4*time.Minute+50*time.Second), false, false, true)
	if resumed.Ready != 0 || resumed.Work != 60 {
		t.Fatalf("bad hydro auto-recovery interval: %+v", resumed)
	}
	extra := Advance("mustard", resumed, now.Add(6*time.Minute), false, false, true)
	if extra.Ready != 1 {
		t.Fatalf("hydroponic crop did not regrow: %+v", extra)
	}
}
func TestRemovalRefundNoMoneyExploit(t *testing.T) {
	if RemovalRefund("aquaponics", 0) != 270 || RemovalRefund("aquaponics", 31) != 108 {
		t.Fatal("structure refund policy invalid")
	}
	if RemovalRefund("rice_crop", 0) != 18 || RemovalRefund("rice_crop", 31) != 0 {
		t.Fatal("harvestable crop must not return cost")
	}
	if RemovalRefund("chicken", 31) != 0 {
		t.Fatal("productive animal refund exploit")
	}
	if RemovalRefund("missing", 0) != 0 {
		t.Fatal("unknown item refund")
	}
}
