package gamedomain

import (
	"math"
	"time"
)

// Durations are real-time seconds, never time speed multipliers. All values are data driven.
// Consumption and production are computed only by the server, independently of browser FPS.
type Good struct {
	Label       string `json:"label"`
	Category    string `json:"category"`
	Price       int    `json:"price"`
	Seconds     int    `json:"seconds,omitempty"`
	Yield       string `json:"yield,omitempty"`
	Amount      int    `json:"amount,omitempty"`
	Food        string `json:"food,omitempty"`
	Housing     string `json:"housing,omitempty"`
	Description string `json:"description"`
}

var Goods = map[string]Good{
	"rice_crop":     {"Lúa nước", "CROP", 18, 120, "paddy", 3, "", "", "Trồng lúa để lấy thóc cho gà, hoặc xay thành gạo."},
	"water_spinach": {"Rau muống", "CROP", 16, 100, "water_spinach", 2, "", "", "Rau muống nuôi cá, hoặc đem bán cho nhà hàng."},
	"mustard":       {"Rau cải", "CROP", 19, 125, "mustard", 2, "", "", "Rau cải ăn được, có thể trồng cạnh aquaponics."},
	"flower":        {"Hoa dại", "CROP", 26, 95, "flower", 1, "", "", "Hoa đã nở nuôi ong tạo mật. Giữ hoa lại để ong hút mật."},
	"chicken":       {"Gà thả vườn", "ANIMAL", 115, 360, "egg", 1, "paddy", "", "Gà ăn thóc, 6 phút khỏe mạnh sẽ cho 1 quả trứng."},
	"frog":          {"Ếch xanh", "ANIMAL", 120, 450, "frog_product", 1, "insect|frog_feed", "water", "Ếch cần nước và côn trùng/cám; trưởng thành thì xuất bán."},
	"fish":          {"Cá rô", "ANIMAL", 110, 420, "fish_product", 1, "water_spinach|fish_feed", "water", "Cá ăn rau muống/cám. Cần thùng hoặc ao có oxy."},
	"bee":           {"Ong mật", "ANIMAL", 135, 330, "honey", 1, "nectar", "hive", "Ong cần tổ và hoa đang nở ở gần để lấy mật."},
	"fence":         {"Hàng rào gỗ", "DECOR", 14, 0, "", 0, "", "", "Các đoạn rào liền kề tự ghép thành hàng rào; khép kín để giữ gà."},
	"flowerpot":     {"Chậu hoa", "DECOR", 55, 0, "", 0, "", "", "Một góc trang trí cho khu vườn."},
	"bench":         {"Ghế gỗ", "DECOR", 75, 0, "", 0, "", "", "Ghế nghỉ chân bên vườn."},
	"tank":          {"Thùng nuôi", "STRUCTURE", 85, 45, "", 0, "", "", "Thùng nước 4×2 ô, nuôi tối đa 8 cá/ếch; oxy đủ khoảng 12 giờ từ mức đầy."},
	"pond":          {"Ao sinh thái", "STRUCTURE", 260, 180, "", 0, "", "", "Ao 4×2 ô, tối đa 8 cá/ếch; oxy đủ khoảng 12 giờ từ mức đầy."},
	"hive":          {"Tổ ong", "STRUCTURE", 100, 60, "", 0, "", "", "Nhà cho ong. Cần có hoa ở gần."},
	"aquaponics":    {"Giàn aquaponics 5×3", "STRUCTURE", 270, 120, "", 0, "", "", "Giàn trồng 5×3, tự cấp nước; oxy đủ khoảng 12 giờ từ mức đầy."},
}

// Anything that may be sold is an inventory good, not a placement prefab.
var SellPrices = map[string]int{"paddy": 12, "rice": 35, "egg": 76, "frog_product": 275, "fish_product": 260, "chicken_product": 300, "honey": 155, "water_spinach": 42, "mustard": 54, "flower": 48, "insect": 7}
var ShopSupplies = map[string]int{"frog_feed": 28, "fish_feed": 25, "medicine": 70, "oxygen": 55, "rice": 45}
var Labels = map[string]string{"paddy": "Thóc", "rice": "Gạo", "egg": "Trứng gà", "frog_product": "Ếch thương phẩm", "fish_product": "Cá thương phẩm", "chicken_product": "Gà thương phẩm", "honey": "Mật ong", "water_spinach": "Rau muống", "mustard": "Rau cải", "flower": "Hoa", "insect": "Côn trùng", "frog_feed": "Cám ếch", "fish_feed": "Cám cá", "medicine": "Thuốc thú y", "oxygen": "Bình oxy", "meal": "Cơm chín", "aid_rice": "Gạo cứu trợ"}

// Oxygen is a server-side timer: with a full tank/pond/rack, production remains
// enabled until oxygen reaches 15%. Each habitat lasts exactly 12 hours.
// OxygenAge is elapsed seconds since the last oxygen refill (not seconds spent
// at the current integer percent). This allows fractional seconds-per-percent
// without losing time when the game is polled frequently or after a refresh.
const OxygenMinimum = 15
const oxygenSpendablePoints = 100 - OxygenMinimum

// OxygenThresholdSeconds is the time for 100% to drop to the 15% cutoff.
func OxygenThresholdSeconds(kind string) int {
	switch kind {
	case "pond", "tank", "aquaponics":
		return CareCycleSeconds
	}
	return 0
}

// OxygenLeftSeconds returns exact integer seconds until growth must pause.
func OxygenLeftSeconds(kind string, rt Runtime) int {
	duration := OxygenThresholdSeconds(kind)
	if duration == 0 || rt.Oxygen <= OxygenMinimum {
		return 0
	}
	age := rt.OxygenAge
	if age < 0 {
		age = 0
	}
	used := (age * oxygenSpendablePoints) / duration
	remainingPoints := rt.Oxygen - OxygenMinimum
	targetSpent := used + remainingPoints
	// ceil(targetSpent * duration / 85) is the first second at 15%.
	requiredAge := (targetSpent*duration + oxygenSpendablePoints - 1) / oxygenSpendablePoints
	return Clamp(requiredAge-age, 0, 86400*365)
}

// Debit elapsed real time with integer arithmetic; outcome cannot depend on
// polling frequency. Once depleted, extra offline time is not credited later.
func DrainOxygen(kind string, rt Runtime, now time.Time) Runtime {
	duration := OxygenThresholdSeconds(kind)
	if duration == 0 {
		return rt
	}
	delta := int(now.Sub(rt.LastTick).Seconds())
	if delta <= 0 {
		return rt
	}
	oldAge := rt.OxygenAge
	if oldAge < 0 {
		oldAge = 0
	}
	newAge := oldAge + delta
	usedBefore := oldAge * oxygenSpendablePoints / duration
	usedAfter := newAge * oxygenSpendablePoints / duration
	rt.Oxygen = Clamp(rt.Oxygen-(usedAfter-usedBefore), 0, 100)
	rt.OxygenAge = newAge
	if rt.Oxygen == 0 {
		rt.OxygenAge = 0
	}
	rt.LastTick = now
	return rt
}

// An oxygen bottle starts a complete care cycle even for an empty habitat.
func RefillOxygen(rt Runtime) Runtime {
	rt.Oxygen = 100
	rt.OxygenAge = 0
	return rt
}

// 100% refund for placement mistakes within 30 seconds, later only a partial
// salvage of structures/decor. Removing crops/livestock later does not repay
// their cost (their production may already have yielded resources).
func RemovalRefund(kind string, elapsedSeconds int) int {
	g, ok := Goods[kind]
	if !ok {
		return 0
	}
	if elapsedSeconds < 30 {
		return g.Price
	}
	if g.Category == "STRUCTURE" || g.Category == "DECOR" {
		return g.Price * 40 / 100
	}
	return 0
}

// After harvest a crop keeps its field/identity; it must rest before being watered again.
const CropRegrowCooldownSeconds = 40

const CareCycleSeconds = 12 * 60 * 60
const FarmerHungerCap = CareCycleSeconds
const AnimalHungerCap = CareCycleSeconds
const CropWaterCap = CareCycleSeconds
const MaxReady = 2

func Clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}
func HasHousing(kind string) bool { return kind == "frog" || kind == "fish" || kind == "bee" }
func Footprint(kind string) (int, int) {
	if kind == "pond" || kind == "tank" {
		return 4, 2
	}
	if kind == "aquaponics" {
		return 5, 3
	}
	return 1, 1
}
func Overlap(x, y int, kind string, otherX, otherY int, otherKind string) bool {
	w, h := Footprint(kind)
	ow, oh := Footprint(otherKind)
	return x < otherX+ow && x+w > otherX && y < otherY+oh && y+h > otherY
}
func CropSpeed(aquaponic bool) int {
	if aquaponic {
		return 120
	}
	return 100
}

type Runtime struct {
	LastTick                                                                     time.Time
	Work, Hunger, Water, Health, Ready, Oxygen, OxygenAge, Starvation, Remainder int
	Sick                                                                         bool
	BuildUntil                                                                   *time.Time
	RegrowUntil                                                                  *time.Time
}

// HarvestCrop resets production but retains the remaining soil moisture.
// LastTick is reset so time before the next growth cycle cannot be credited.
func HarvestCrop(rt Runtime, now time.Time) Runtime {
	rt.Work, rt.Remainder, rt.Ready = 0, 0, 0
	rt.LastTick = now
	until := now.Add(CropRegrowCooldownSeconds * time.Second)
	rt.RegrowUntil = &until
	return rt
}

func CropRegrowLeft(rt Runtime, now time.Time) int {
	if rt.RegrowUntil == nil || !now.Before(*rt.RegrowUntil) {
		return 0
	}
	return int(math.Ceil(rt.RegrowUntil.Sub(now).Seconds()))
}

// A harvested crop cannot be watered during recovery. Afterward it resumes
// automatically while moisture remains; dry soil waits for another watering.
func CanWaterCrop(rt Runtime, now time.Time) bool {
	return CropRegrowLeft(rt, now) == 0
}

// WaterCrop starts the next cycle at the watering instant. Growth must never
// borrow elapsed cooldown/waiting time, even if the farm has not been polled.
func WaterCrop(rt Runtime, now time.Time) Runtime {
	rt.Water = CropWaterCap
	rt.RegrowUntil = nil
	rt.LastTick = now
	return rt
}

// Advance is pure: no dependence on DB, rendering, or random clock calls.
// Production is paused by hunger, sickness and unavailable requirements. No arbitrary boosts on feeding.
func Advance(kind string, rt Runtime, now time.Time, housed, floral, aquaponic bool) Runtime {
	g, ok := Goods[kind]
	if !ok {
		return rt
	}
	if rt.LastTick.IsZero() {
		rt.LastTick = now
		return rt
	}
	previousTick := rt.LastTick
	delta := int(now.Sub(rt.LastTick).Seconds())
	if delta <= 0 {
		return rt
	}
	rt.LastTick = rt.LastTick.Add(time.Duration(delta) * time.Second)
	if delta > 86400*30 {
		delta = 86400 * 30
	} // protect from bogus system clock jumps
	if g.Category == "CROP" {
		// A harvested bed rests briefly, then resumes while water remains.
		if rt.RegrowUntil != nil {
			if now.Before(*rt.RegrowUntil) {
				rt.Water = Clamp(rt.Water-delta, 0, CropWaterCap)
				return rt
			}
			// Never credit the recovery interval as growing time or free moisture.
			start := *rt.RegrowUntil
			if previousTick.After(start) {
				start = previousTick
			}
			rt.Water = Clamp(rt.Water-int(start.Sub(previousTick).Seconds()), 0, CropWaterCap)
			if !aquaponic && rt.Water == 0 {
				return rt
			}
			rt.RegrowUntil = nil
			rt.LastTick = start
			delta = int(now.Sub(start).Seconds())
			if delta <= 0 {
				return rt
			}
		}
		active := Clamp(rt.Water, 0, delta)
		if aquaponic {
			active = delta
		}
		rt.Water = Clamp(rt.Water-delta, 0, CropWaterCap)
		// An aquaponic bed has a modest, bounded benefit, not an instantaneous harvest.
		credit := active*CropSpeed(aquaponic) + rt.Remainder
		rt.Work = Clamp(rt.Work+credit/100, 0, g.Seconds)
		rt.Remainder = credit % 100
		if rt.Work >= g.Seconds {
			rt.Ready = 1
		}
		rt.LastTick = now // no second credit when server polls again
		return rt
	}
	if g.Category != "ANIMAL" {
		return rt
	}
	beforeHunger := rt.Hunger
	active := Clamp(beforeHunger, 0, delta)
	rt.Hunger = Clamp(rt.Hunger-delta, 0, AnimalHungerCap)
	if rt.Sick || (HasHousing(kind) && !housed) || (kind == "bee" && !floral) {
		active = 0
	}
	// Water stock is handled on tank/pond by an independent, slowly declining quality meter.
	rt.Work += active
	if g.Seconds > 0 && rt.Work >= g.Seconds {
		gained := rt.Work / g.Seconds
		rt.Ready = Clamp(rt.Ready+gained, 0, MaxReady)
		rt.Work = rt.Work % g.Seconds
		if rt.Ready == MaxReady {
			rt.Work = 0
		}
	}
	// Track cumulative consecutive starvation independent of login/poll frequency.
	hungryFor := Clamp(delta-beforeHunger, 0, delta)
	previous := rt.Starvation
	if hungryFor > 0 {
		rt.Starvation = Clamp(rt.Starvation+hungryFor, 0, 86400*365)
	} else {
		rt.Starvation = 0
	}
	badHours := func(seconds int) int {
		if seconds <= CareCycleSeconds {
			return 0
		}
		return (seconds - CareCycleSeconds) / 3600
	}
	steps := badHours(rt.Starvation) - badHours(previous)
	if steps > 0 {
		rt.Health = Clamp(rt.Health-steps*3, 20, 100)
	}
	if rt.Health <= 35 {
		rt.Sick = true
	}
	return rt
}

// Uses flood-fill from the map edge. A ring of fences must be entirely closed to be considered an enclosure.
// Fences are barriers; a chicken on a reachable outside tile is free roaming.
func Enclosed(x, y int, fences map[[2]int]bool) bool {
	if fences[[2]int{x, y}] || !ValidTile(x, y) {
		return false
	}
	visited := map[[2]int]bool{}
	q := make([][2]int, 0, Width*Height)
	for i := 0; i < Width; i++ {
		for _, j := range []int{0, Height - 1} {
			q = append(q, [2]int{i, j})
		}
	}
	for j := 0; j < Height; j++ {
		for _, i := range []int{0, Width - 1} {
			q = append(q, [2]int{i, j})
		}
	}
	for len(q) > 0 {
		p := q[0]
		q = q[1:]
		if p[0] < 0 || p[0] >= Width || p[1] < 0 || p[1] >= Height || visited[p] || fences[p] {
			continue
		}
		visited[p] = true
		if p[0] == x && p[1] == y {
			return false
		}
		for _, d := range [][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}} {
			q = append(q, [2]int{p[0] + d[0], p[1] + d[1]})
		}
	}
	return true
}
func Progress(kind string, r Runtime) float64 {
	g, ok := Goods[kind]
	if !ok || g.Seconds <= 0 {
		return 0
	}
	if r.Ready > 0 {
		return 1
	}
	return math.Min(1, float64(r.Work)/float64(g.Seconds))
}
