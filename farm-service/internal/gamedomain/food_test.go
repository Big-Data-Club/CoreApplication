package gamedomain

import "testing"

func TestHungerStopsWork(t *testing.T) {
	if FarmerCanWork(0) || !FarmerCanWork(1) {
		t.Fatal("hunger gate")
	}
}
func TestEmergencyRiceRules(t *testing.T) {
	for _, tc := range []struct {
		coins, hunger int
		inv           map[string]int
		allowed       bool
	}{
		{0, 0, map[string]int{}, true},
		{44, 0, map[string]int{}, true},
		{45, 0, map[string]int{}, false},
		{0, 1, map[string]int{}, false},
		{0, 0, map[string]int{"rice": 1}, false},
		{0, 0, map[string]int{"meal": 1}, false},
		{0, 0, map[string]int{"paddy": 2}, false},
		{0, 0, map[string]int{"aid_rice": 1}, false},
	} {
		if got := CanReceiveEmergencyRice(tc.coins, tc.hunger, tc.inv); got != tc.allowed {
			t.Fatalf("coins %d hunger %d inv %+v: got %v", tc.coins, tc.hunger, tc.inv, got)
		}
	}
}
func TestRiceIsMoreExpensiveToBuyThanSell(t *testing.T) {
	if ShopSupplies["rice"] <= SellPrices["rice"] {
		t.Fatal("free rice arbitrage")
	}
	if _, canBuyMeal := ShopSupplies["meal"]; canBuyMeal {
		t.Fatal("cannot bypass cooking via shop")
	}
	if _, canSellAid := SellPrices["aid_rice"]; canSellAid {
		t.Fatal("emergency rice must not be tradable")
	}
}
