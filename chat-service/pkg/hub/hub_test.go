package hub

import (
	"fmt"
	"github.com/redis/go-redis/v9"
	"sync"
	"testing"
	"time"
)

func TestAdmissionAndDuplicateRemoval(t *testing.T) {
	h := New(nil, Limits{MaxClients: 2, MaxClientsPerUser: 1})
	defer h.Shutdown()
	a := NewClient(h, nil, 1, "", nil, []int64{1, 2})
	if !h.RegisterClient(a) || !h.RegisterClient(a) {
		t.Fatal("admission must be idempotent")
	}
	if h.RegisterClient(NewClient(h, nil, 1, "", nil, []int64{1})) {
		t.Fatal("user limit bypassed")
	}
	if h.CanAdmit(1) {
		t.Fatal("preflight ignored user capacity")
	}
	b := NewClient(h, nil, 2, "", nil, []int64{1})
	if !h.RegisterClient(b) || h.RegisterClient(NewClient(h, nil, 3, "", nil, []int64{1})) {
		t.Fatal("replica limit bypassed")
	}
	h.UnregisterClient(a)
	h.UnregisterClient(a)
	if h.LocalCount(1) != 1 || h.LocalCount(2) != 0 {
		t.Fatal("membership leaked")
	}
	if !h.RegisterClient(NewClient(h, nil, 1, "", nil, []int64{1})) {
		t.Fatal("capacity not released")
	}
}

func TestSlowClientDoesNotBlockHealthyClient(t *testing.T) {
	h := New(nil)
	defer h.Shutdown()
	slow := NewClient(h, nil, 1, "", nil, []int64{1})
	fast := NewClient(h, nil, 2, "", nil, []int64{1})
	h.RegisterClient(slow)
	h.RegisterClient(fast)
	for i := 0; i < ClientSendBuffer; i++ {
		slow.enqueue([]byte("old"))
	}
	h.fanOut(&redis.Message{Channel: "chat:ch:1", Payload: `{"type":"message"}`})
	if h.LocalCount(1) != 1 {
		t.Fatal("slow client not removed")
	}
	select {
	case <-fast.send:
	default:
		t.Fatal("healthy delivery blocked")
	}
}

func TestConcurrentFanOutAndDisconnect(t *testing.T) {
	h := New(nil)
	defer h.Shutdown()
	c := NewClient(h, nil, 1, "", nil, []int64{1})
	h.RegisterClient(c)
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				h.fanOut(&redis.Message{Channel: "chat:ch:1", Payload: `{"type":"message"}`})
				h.UnregisterClient(c)
			}
		}()
	}
	wg.Wait()
	if h.LocalCount(1) != 0 {
		t.Fatal("closed client retained")
	}
}

func TestRoomOrderAndAccessRevocation(t *testing.T) {
	h := New(nil)
	defer h.Shutdown()
	c := NewClient(h, nil, 1, "", nil, []int64{1, 2})
	h.RegisterClient(c)
	queue := make(chan *redis.Message, 10)
	h.wg.Add(1)
	go func() { defer h.wg.Done(); h.broadcastWorker(queue) }()
	for i := 0; i < 10; i++ {
		queue <- &redis.Message{Channel: "chat:ch:1", Payload: fmt.Sprint(i)}
	}
	for i := 0; i < 10; i++ {
		select {
		case data := <-c.send:
			if string(data) != fmt.Sprint(i) {
				t.Fatal("room order changed")
			}
		case <-time.After(time.Second):
			t.Fatal("delivery timeout")
		}
	}
	h.fanOut(&redis.Message{Channel: "chat:ch:1", Payload: `{"type":"access_changed"}`})
	if h.LocalCount(1) != 0 || h.LocalCount(2) != 0 {
		t.Fatal("revoked socket still subscribed")
	}
}

func TestMalformedRoomAndFrameFlood(t *testing.T) {
	for _, key := range []string{"", "chat:ch:", "chat:ch:0", "chat:ch:-1", "chat:ch:9223372036854775808", "other:1"} {
		var id int64
		if parseChannelID(key, &id) {
			t.Fatalf("accepted %q", key)
		}
	}
	now := time.Now()
	c := &Client{frameTokens: 40, lastFrame: now}
	for i := 0; i < 40; i++ {
		if !c.allowFrame(now) {
			t.Fatal("burst denied")
		}
	}
	if c.allowFrame(now) {
		t.Fatal("flood accepted")
	}
	if !c.allowFrame(now.Add(100 * time.Millisecond)) {
		t.Fatal("bucket did not refill")
	}
}

func BenchmarkFanOut1000(b *testing.B) {
	h := New(nil)
	defer h.Shutdown()
	clients := make([]*Client, 1000)
	for i := range clients {
		clients[i] = NewClient(h, nil, int64(i+1), "", nil, []int64{1})
		h.RegisterClient(clients[i])
	}
	msg := &redis.Message{Channel: "chat:ch:1", Payload: `{"type":"message","payload":{"body":"hello"}}`}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		h.fanOut(msg)
		for _, c := range clients {
			<-c.send
		}
	}
}
