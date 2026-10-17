package gamedomain

import "math"

// Species are the real-farm matching capabilities. A vegetable request may map
// to a number of virtual crop species; livestock kinds are strictly supported.
var Species = map[string]string{
	"chicken": "Gà", "frog": "Ếch", "fish": "Cá", "bee": "Ong", "vegetable": "Vườn rau",
}

const Width = 20
const Height = 14

func Blocked(x, y int) bool {
	return (x >= 1 && x <= 3 && y >= 1 && y <= 3) || (x == 0 && y == 0)
}
func ValidTile(x, y int) bool { return x >= 0 && x < Width && y >= 0 && y < Height && !Blocked(x, y) }
func Level(xp int) int        { return int(math.Sqrt(float64(xp)/110)) + 1 }
