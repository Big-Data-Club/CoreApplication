package main

import "time"

// Pause the whole dispatcher after failure, so a backlog cannot bypass the
// per-attempt retry schedule. Successful delivery resets the cooldown.
type learningBackoff struct {
	delay       time.Duration
	nextAttempt time.Time
}

func (b *learningBackoff) failed(now time.Time) time.Duration {
	if b.delay == 0 {
		b.delay = 5 * time.Second
	} else {
		b.delay *= 2
		if b.delay > time.Minute {
			b.delay = time.Minute
		}
	}
	b.nextAttempt = now.Add(b.delay)
	return b.delay
}
