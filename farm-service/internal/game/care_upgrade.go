package game

import domain "bdc/farm-service/internal/gamedomain"

// upgradeCareTimers refreshes legacy farms once, under their existing row lock.
// Progress, ready harvests, inventory, and player coins are left intact.
func upgradeCareTimers(g *gameTx) []*gameEntity {
	g.Life.Hunger = domain.FarmerHungerCap
	g.Life.LastTick = g.Now
	changed := make([]*gameEntity, 0, len(g.Entities))
	for i := range g.Entities {
		obj := &g.Entities[i]
		obj.RT.LastTick = g.Now
		switch obj.Category {
		case "ANIMAL":
			obj.RT.Hunger = domain.AnimalHungerCap
			obj.RT.Starvation = 0
			obj.RT.Health = 100
			obj.RT.Sick = false
		case "CROP":
			obj.RT.Water = domain.CropWaterCap
		case "STRUCTURE":
			if domain.OxygenThresholdSeconds(obj.Kind) > 0 {
				obj.RT.Oxygen = 100
				obj.RT.OxygenAge = 0
			}
		}
		changed = append(changed, obj)
	}
	return changed
}
