package gamedomain

import "testing"

func TestBlocked(t *testing.T) {
	if !Blocked(2, 2) || ValidTile(2, 2) || !ValidTile(4, 4) || ValidTile(Width, 2) {
		t.Fatal("tile rule failed")
	}
}
func TestCatalogConsistency(t *testing.T) {
	if Goods["frog"].Category != "ANIMAL" || Goods["pond"].Category != "STRUCTURE" || Goods["rice_crop"].Category != "CROP" {
		t.Fatal("bad economy catalog")
	}
	if _, ok := Species["frog"]; !ok {
		t.Fatal("frog cannot connect to real farm")
	}
	if _, ok := Species["duck"]; ok {
		t.Fatal("unsupported species must not be offered")
	}
}
