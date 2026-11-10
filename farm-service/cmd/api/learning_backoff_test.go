package main

import (
	"testing"
	"time"
)

func TestLearningBackoffCapsAndResets(t *testing.T) {
	var b learningBackoff
	now := time.Unix(1000, 0)
	for _, want := range []time.Duration{5, 10, 20, 40, 60, 60} {
		want *= time.Second
		if got := b.failed(now); got != want || !b.nextAttempt.Equal(now.Add(want)) {
			t.Fatalf("delay=%v next=%v, want %v", got, b.nextAttempt, want)
		}
		now = b.nextAttempt
	}
	b = learningBackoff{}
	if got := b.failed(now); got != 5*time.Second {
		t.Fatalf("delay after reset = %v", got)
	}
}
