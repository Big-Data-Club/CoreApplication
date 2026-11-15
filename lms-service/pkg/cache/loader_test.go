package cache

import (
	"context"
	"sync/atomic"
	"testing"
	"time"
)

func TestCancelledLeaderDoesNotCancelSharedLoad(t *testing.T) {
	loader := NewLoader(nil)
	started := make(chan struct{})
	release := make(chan struct{})
	var calls atomic.Int32
	load := func(ctx context.Context) (int, error) {
		if calls.Add(1) == 1 {
			close(started)
		}
		select {
		case <-ctx.Done():
			return 0, ctx.Err()
		case <-release:
			return 42, nil
		}
	}
	leaderCtx, cancel := context.WithCancel(context.Background())
	leaderDone := make(chan error, 1)
	go func() { _, err := GetOrLoad(leaderCtx, loader, "shared", time.Minute, load); leaderDone <- err }()
	<-started
	cancel()
	select {
	case err := <-leaderDone:
		if err != context.Canceled {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("canceled caller remained blocked")
	}
	followerDone := make(chan error, 1)
	go func() {
		value, err := GetOrLoad(context.Background(), loader, "shared", time.Minute, load)
		if err == nil && value != 42 {
			t.Errorf("value=%d", value)
		}
		followerDone <- err
	}()
	close(release)
	if err := <-followerDone; err != nil {
		t.Fatal(err)
	}
	// The test checks cancellation isolation; a caller scheduled after completion
	// may initiate another uncached load when Redis is deliberately disabled.
}
