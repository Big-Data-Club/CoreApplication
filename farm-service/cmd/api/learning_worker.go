package main

import (
	"context"
	"time"
)

// Wake signals are hints; the durable outbox remains authoritative. The fallback
// recovers pending rows after restarts, missed signals, and writes on replicas.
func runLearningWorker(ctx context.Context, wake <-chan struct{}, dispatch func(context.Context) (bool, error), report func(error, time.Duration), idle time.Duration) {
	var backoff learningBackoff
	timer := time.NewTimer(0) // Drain pre-existing work at startup.
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-wake:
		case <-timer.C:
		}
		if remaining := time.Until(backoff.nextAttempt); remaining > 0 {
			timer.Reset(remaining)
			continue
		}
		delay := idle
		for i := 0; i < 20; i++ {
			if ctx.Err() != nil {
				return
			}
			c, cancel := context.WithTimeout(ctx, 6*time.Second)
			sent, err := dispatch(c)
			cancel()
			if err != nil {
				delay = backoff.failed(time.Now())
				report(err, delay)
				break
			}
			if !sent {
				delay = idle
				break
			}
			backoff = learningBackoff{}
			// Continue full batches immediately, without needing another signal.
			delay = 0
		}
		timer.Reset(delay)
	}
}
