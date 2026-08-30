package runtime

import "testing"

func TestValidPodName(t *testing.T) {
	valid := []string{"terminal-u2-l3-abc123", "a", "sandbox-42"}
	invalid := []string{"", "../secrets", "Terminal-1", "-terminal", "terminal-", "terminal/session"}
	for _, value := range valid {
		if !validPodName(value) {
			t.Fatalf("expected %q to be valid", value)
		}
	}
	for _, value := range invalid {
		if validPodName(value) {
			t.Fatalf("expected %q to be invalid", value)
		}
	}
}
