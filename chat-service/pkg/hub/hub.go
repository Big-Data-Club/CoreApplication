// Package hub implements a scalable WebSocket broadcast mechanism backed by
// Redis Pub/Sub. This design allows running multiple chat-service replicas
// behind a load balancer without sticky sessions:
//
//   Client A (replica 1) ──send──► Redis channel "chat:ch:42" ──► all replicas
//                                                                     │
//   Client B (replica 1) ◄──recv──────────────────────────────────────┘
//   Client C (replica 2) ◄──recv──────────────────────────────────────┘
//
// Memory layout per replica:
//   Hub.rooms: map[channelID int64] -> set[*Client]
//   Each Client owns one goroutine for reading from WS and one for writing.
//   The writePump drains a buffered channel - slow clients are dropped after
//   ClientSendBuffer fills up, preventing any single slow client from blocking
//   the broadcast loop.
package hub

import (
	"context"
	"encoding/json"
	"sync"
	"time"

	"chat-service/pkg/logger"

	"github.com/redis/go-redis/v9"
)

const (
	// PubSubPrefix is the Redis key prefix for per-channel Pub/Sub topics.
	PubSubPrefix = "chat:ch:"

	// ClientSendBuffer is the size of each client's outbound channel.
	// When full the client is considered "slow" and dropped.
	ClientSendBuffer = 256

	// MaxMessageSize is the maximum raw WebSocket frame size we accept (bytes).
	MaxMessageSize = 8 * 1024 // 8 KB - well above our 4000-char body limit

	// WriteWait is the deadline for a single write to the WebSocket.
	WriteWait = 10 * time.Second

	// PongWait is the maximum time to wait for a pong from the client.
	PongWait = 60 * time.Second

	// PingPeriod sends pings at this interval (must be < PongWait).
	PingPeriod = (PongWait * 9) / 10

	// broadcastWorkers is the number of goroutines that relay Redis messages
	// to local WebSocket clients. Tune to CPU count × 2.
	broadcastWorkers = 8
)

// EventType identifies the kind of WSEvent on the wire.
type EventType string

const (
	EventMessage  EventType = "message"
	EventDelete   EventType = "delete"
	EventTyping   EventType = "typing"
	EventJoin     EventType = "join"
	EventLeave    EventType = "leave"
	EventPing     EventType = "ping"
	EventAck      EventType = "ack"
)

// WSEvent is the JSON envelope sent over WebSocket and through Redis Pub/Sub.
type WSEvent struct {
	Type      EventType   `json:"type"`
	ChannelID int64       `json:"channel_id"`
	Payload   interface{} `json:"payload,omitempty"`
	Timestamp time.Time   `json:"ts"`
}

// MessagePayload is the Payload for EventMessage / EventDelete.
type MessagePayload struct {
	ID           int64  `json:"id"`
	SenderID     int64  `json:"sender_id"`
	SenderName   string `json:"sender_name"`
	SenderAvatar string `json:"sender_avatar,omitempty"`
	Body         string `json:"body"`
	IsDeleted    bool   `json:"is_deleted,omitempty"`
}

// TypingPayload is the Payload for EventTyping.
type TypingPayload struct {
	UserID   int64  `json:"user_id"`
	UserName string `json:"user_name"`
}

// -------------------------------------------------------------------
// Hub
// -------------------------------------------------------------------

// Hub manages the in-process registry of active WebSocket clients and
// bridges local broadcasts with Redis Pub/Sub for multi-replica support.
type Hub struct {
	mu    sync.RWMutex
	rooms map[int64]map[*Client]struct{} // channelID -> set of local clients

	register   chan *Client
	unregister chan *Client

	// incoming is the queue of raw Redis Pub/Sub messages to fan out locally.
	incoming chan *redis.Message

	rdb    *redis.Client
	pubsub *redis.PubSub

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

// New creates a Hub. Call Run() in a goroutine after construction.
func New(rdb *redis.Client) *Hub {
	ctx, cancel := context.WithCancel(context.Background())
	return &Hub{
		rooms:      make(map[int64]map[*Client]struct{}),
		register:   make(chan *Client, 512),
		unregister: make(chan *Client, 512),
		incoming:   make(chan *redis.Message, 4096),
		rdb:        rdb,
		ctx:        ctx,
		cancel:     cancel,
	}
}

// Run starts the hub event loop and Redis subscriber goroutines.
// It blocks until ctx is cancelled (via Shutdown).
func (h *Hub) Run() {
	logger.Infof("hub: starting (workers=%d, queueSize=%d, pubSubPattern=%s)",
		broadcastWorkers, 4096, PubSubPrefix+"*")

	// Start Redis Pub/Sub subscriber
	h.pubsub = h.rdb.PSubscribe(h.ctx, PubSubPrefix+"*")

	// Forward Redis messages to the incoming queue
	h.wg.Add(1)
	go func() {
		defer h.wg.Done()
		ch := h.pubsub.Channel(redis.WithChannelSize(4096))
		for msg := range ch {
			select {
			case h.incoming <- msg:
			default:
				// Drop if incoming is full - prevents Redis subscriber from blocking
				logger.Warn("hub: incoming queue full, dropping Redis message")
			}
		}
	}()

	// Broadcast worker pool: fan out incoming Redis messages to local clients
	for i := 0; i < broadcastWorkers; i++ {
		h.wg.Add(1)
		go func() {
			defer h.wg.Done()
			h.broadcastWorker()
		}()
	}

	// Main event loop: register / unregister clients
	for {
		select {
		case client := <-h.register:
			h.addClient(client)

		case client := <-h.unregister:
			h.removeClient(client)

		case <-h.ctx.Done():
			// Drain remaining register/unregister events
			for {
				select {
				case c := <-h.unregister:
					h.removeClient(c)
				default:
					return
				}
			}
		}
	}
}

// Shutdown gracefully stops the hub.
func (h *Hub) Shutdown() {
	logger.Info("hub: shutting down...")
	h.cancel()
	if h.pubsub != nil {
		_ = h.pubsub.Close()
	}
	h.wg.Wait()
	logger.Info("hub: stopped cleanly")
}

// Publish serialises event to JSON and publishes to the Redis channel for
// the given chatChannelID. All replicas (including this one) receive it via
// their Pub/Sub subscriber.
func (h *Hub) Publish(ctx context.Context, channelID int64, event WSEvent) error {
	data, err := json.Marshal(event)
	if err != nil {
		return err
	}
	logger.Debugf("hub: publish type=%s channelID=%d localClients=%d",
		event.Type, channelID, h.LocalCount(channelID))
	return h.rdb.Publish(ctx, redisKey(channelID), data).Err()
}

// RegisterClient queues a client for registration.
func (h *Hub) RegisterClient(c *Client) {
	h.register <- c
}

// UnregisterClient queues a client for removal.
func (h *Hub) UnregisterClient(c *Client) {
	h.unregister <- c
}

// LocalCount returns the number of locally connected clients for a channel.
func (h *Hub) LocalCount(channelID int64) int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.rooms[channelID])
}

// -------------------------------------------------------------------
// internal helpers
// -------------------------------------------------------------------

func (h *Hub) addClient(c *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	for _, chID := range c.channelIDs {
		if h.rooms[chID] == nil {
			h.rooms[chID] = make(map[*Client]struct{})
		}
		h.rooms[chID][c] = struct{}{}
	}
	totalLocal := h.totalLocalClients()
	logger.Infof("hub: client connected userID=%d channels=%v totalLocal=%d",
		c.UserID, c.channelIDs, totalLocal)
}

func (h *Hub) removeClient(c *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	for _, chID := range c.channelIDs {
		if room, ok := h.rooms[chID]; ok {
			delete(room, c)
			if len(room) == 0 {
				delete(h.rooms, chID)
			}
		}
	}
	close(c.send)
	totalLocal := h.totalLocalClients()
	logger.Infof("hub: client disconnected userID=%d totalLocal=%d", c.UserID, totalLocal)
}

// broadcastWorker receives raw Redis messages and fan-outs to matching local clients.
func (h *Hub) broadcastWorker() {
	for {
		select {
		case msg, ok := <-h.incoming:
			if !ok {
				return
			}
			h.fanOut(msg)
		case <-h.ctx.Done():
			// Drain remaining
			for {
				select {
				case msg := <-h.incoming:
					h.fanOut(msg)
				default:
					return
				}
			}
		}
	}
}

func (h *Hub) fanOut(msg *redis.Message) {
	// Parse channel ID from key "chat:ch:<id>"
	var channelID int64
	if !parseChannelID(msg.Channel, &channelID) {
		return
	}

	data := []byte(msg.Payload)

	h.mu.RLock()
	room := h.rooms[channelID]
	// Copy client references under read lock to minimise lock hold time
	clients := make([]*Client, 0, len(room))
	for c := range room {
		clients = append(clients, c)
	}
	h.mu.RUnlock()

	for _, c := range clients {
		select {
		case c.send <- data:
			// delivered
		default:
			// Client is too slow - drop it. The writePump will detect the closed
			// channel and terminate the connection.
			logger.Warnf("hub: slow client %d, dropping", c.UserID)
			h.UnregisterClient(c)
		}
	}
}

func redisKey(channelID int64) string {
	return PubSubPrefix + int64ToString(channelID)
}

// totalLocalClients sums clients across all rooms. Caller must hold mu (read or write).
func (h *Hub) totalLocalClients() int {
	total := 0
	for _, room := range h.rooms {
		total += len(room)
	}
	return total
}

func int64ToString(n int64) string {
	buf := [20]byte{}
	pos := len(buf)
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	for n > 0 {
		pos--
		buf[pos] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		pos--
		buf[pos] = '-'
	}
	return string(buf[pos:])
}

func parseChannelID(key string, out *int64) bool {
	prefix := PubSubPrefix
	if len(key) <= len(prefix) {
		return false
	}
	s := key[len(prefix):]
	var n int64
	for _, ch := range s {
		if ch < '0' || ch > '9' {
			return false
		}
		n = n*10 + int64(ch-'0')
	}
	*out = n
	return true
}
