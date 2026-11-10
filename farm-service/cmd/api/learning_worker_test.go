package main

import (
	"context"
	"errors"
	"testing"
	"time"
)

func awaitDispatch(t *testing.T, calls <-chan struct{}) {
	t.Helper()
	select {
	case <-calls:
	case <-time.After(2 * time.Second):
		t.Fatal("dispatcher did not wake")
	}
}

func TestLearningWorkerStartupWakeAndIdle(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	wake := make(chan struct{}, 1)
	calls := make(chan struct{}, 10)
	done := make(chan struct{})
	go func() {
		defer close(done)
		runLearningWorker(ctx, wake, func(context.Context) (bool, error) {
			calls <- struct{}{}
			return false, nil
		}, func(error, time.Duration) { t.Error("unexpected failure") }, time.Hour)
	}()
	awaitDispatch(t, calls) // startup recovery
	wake <- struct{}{}
	awaitDispatch(t, calls)
	select {
	case <-calls:
		t.Fatal("empty queue caused additional polling")
	case <-time.After(30 * time.Millisecond):
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("idle worker did not stop")
	}
}

func TestLearningWorkerFallback(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	calls := make(chan struct{}, 10)
	go runLearningWorker(ctx, nil, func(context.Context) (bool, error) {
		select {
		case calls <- struct{}{}:
		case <-ctx.Done():
		}
		return false, nil
	}, func(error, time.Duration) {}, 20*time.Millisecond)
	awaitDispatch(t, calls)
	awaitDispatch(t, calls) // missed notification / another replica
}

func TestLearningWorkerDrainsMultipleBatches(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	drained := make(chan struct{})
	count := 0
	go runLearningWorker(ctx, nil, func(context.Context) (bool, error) {
		count++
		if count == 46 {
			close(drained)
			return false, nil
		}
		return true, nil
	}, func(error, time.Duration) {}, time.Hour)
	awaitDispatch(t, drained)
}

func TestLearningWorkerWakeCannotBypassFailureCooldown(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	wake := make(chan struct{}, 1)
	calls := make(chan struct{}, 10)
	failed := make(chan time.Duration, 1)
	go runLearningWorker(ctx, wake, func(context.Context) (bool, error) {
		calls <- struct{}{}
		return true, errors.New("LMS unavailable")
	}, func(_ error, delay time.Duration) { failed <- delay }, time.Hour)
	awaitDispatch(t, calls)
	select {
	case delay := <-failed:
		if delay != 5*time.Second {
			t.Fatalf("cooldown = %v", delay)
		}
	case <-time.After(time.Second):
		t.Fatal("failure was not reported")
	}
	wake <- struct{}{}
	select {
	case <-calls:
		t.Fatal("notification bypassed failure cooldown")
	case <-time.After(30 * time.Millisecond):
	}
}
