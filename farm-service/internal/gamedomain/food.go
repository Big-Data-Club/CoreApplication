package gamedomain

// Emergency rice is only an escape hatch. It is non-tradeable inventory and can
// only be consumed when cooking a meal. The checks are repeated on the Go server
// under the locked farm transaction; a forged browser request cannot bypass them.
func CanReceiveEmergencyRice(coins, hunger int, inventory map[string]int) bool {
	return hunger == 0 && coins < ShopSupplies["rice"] &&
		inventory["rice"] == 0 && inventory["meal"] == 0 &&
		inventory["aid_rice"] == 0 && inventory["paddy"] < 2
}

// A hungry farmer may still mill, cook or eat to get unstuck. Farming, selling,
// buying optional supplies and animal care all require energy.
func FarmerCanWork(hunger int) bool { return hunger > 0 }
