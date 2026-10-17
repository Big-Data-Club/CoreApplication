// Package service owns game rules that do not depend on HTTP or PostgreSQL.
package service

type HarvestSubject struct {
	Kind       string
	AgeSeconds int
	Ready      int
	Hunger     int
	Sick       bool
	Health     int
	Housed     bool
	HasOxygen  bool
}

// HarvestViolation returns a player-facing reason, or an empty string when the
// action is allowed. The handler separately maps a missing entity to HTTP 404.
func HarvestViolation(o HarvestSubject, action string) string {
	if action == "SELL_CHICKEN" {
		if o.Kind != "chicken" || o.AgeSeconds < 420 || o.Hunger == 0 || o.Sick || o.Health < 65 {
			return "Gà cần trưởng thành, no và khỏe trước khi xuất bán"
		}
	} else if action != "HARVEST" || o.Ready == 0 {
		return "Chưa đến lúc thu hoạch"
	}
	if (o.Kind == "frog" || o.Kind == "fish") && (o.Hunger == 0 || o.Sick || !o.Housed || !o.HasOxygen) {
		return "Cá/ếch cần no, khỏe và ao có đủ oxy"
	}
	return ""
}
