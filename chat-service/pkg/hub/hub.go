// Package hub implements a scalable WebSocket broadcast mechanism backed by
// Redis Pub/Sub. This design allows running multiple chat-service replicas
// behind a load balancer without sticky sessions:
//
//	Client A (replica 1) ──send──► Redis channel "chat:ch:42" ──► all replicas
//	                                                                  │
//	Client B (replica 1) ◄──recv──────────────────────────────────────┘
//	Client C (replica 2) ◄──recv──────────────────────────────────────┘
//
// Memory layout per replica:
//
//	Hub.rooms: map[channelID int64] -> set[*Client]
//	Each Client owns one goroutine for reading from WS and one for writing.
//	The writePump drains a buffered channel - slow clients are dropped after
//	ClientSendBuffer fills up, preventing any single slow client from blocking
//	the broadcast loop.
package hub

import (
	"context"
	"encoding/json"
	"strconv"
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
	ClientSendBuffer = 64

	// MaxMessageSize is the maximum raw WebSocket frame size we accept (bytes).
	MaxMessageSize = 32 * 1024 // includes JSON escaping for 4000 Unicode characters

	// WriteWait is the deadline for a single write to the WebSocket.
	WriteWait = 10 * time.Second

	// PongWait is the maximum time to wait for a pong from the client.
	PongWait = 60 * time.Second

	// PingPeriod sends pings at this interval (must be < PongWait).
	PingPeriod = (PongWait * 9) / 10

	// PresenceTTL allows one missed ping while making stale connections disappear
	// promptly. It is stored in Redis, therefore works across replicas.
	PresenceTTL = 90 * time.Second

	// broadcastWorkers is the number of goroutines that relay Redis messages
	// to local WebSocket clients. Tune to CPU count × 2.
	broadcastWorkers = 8
)

// EventType identifies the kind of WSEvent on the wire.
type EventType string

const (
	EventMessage       EventType = "message"
	EventDelete        EventType = "delete"
	EventEdit          EventType = "edit"
	EventTyping        EventType = "typing"
	EventJoin          EventType = "join"
	EventLeave         EventType = "leave"
	EventPing          EventType = "ping"
	EventAck           EventType = "ack"
	EventAccessChanged EventType = "access_changed"
)

// WSEvent is the JSON envelope sent over WebSocket and through Redis Pub/Sub.
type WSEvent struct {
	Type      EventType   `json:"type"`
	ChannelID int64       `json:"channel_id"`
	Payload   interface{} `json:"payload,omitempty"`
	Timestamp time.Time   `json:"ts"`
}

// MessagePayload is the Payload for EventMessage / EventDelete / EventEdit.
type MessagePayload struct {
	ID               int64               `json:"id"`
	SenderID         int64               `json:"sender_id"`
	SenderName       string              `json:"sender_name"`
	SenderAvatar     string              `json:"sender_avatar,omitempty"`
	Body             string              `json:"body"`
	IsDeleted        bool                `json:"is_deleted,omitempty"`
	IsEdited         bool                `json:"is_edited,omitempty"`
	ParentID         *int64              `json:"parent_id,omitempty"`
	ParentSenderName string              `json:"parent_sender_name,omitempty"`
	ParentBody       string              `json:"parent_body,omitempty"`
	Attachments      []AttachmentPayload `json:"attachments,omitempty"`
}

type AttachmentPayload struct {
	ID        string    `json:"id"`
	FileName  string    `json:"file_name"`
	MimeType  string    `json:"mime_type"`
	SizeBytes int64     `json:"size_bytes"`
	CreatedAt time.Time `json:"created_at"`
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
// Limits bound connection memory per replica. Redis still handles cross-replica delivery.
type Limits struct {
	MaxClients        int
	MaxClientsPerUser int
}

type Hub struct {
	mu          sync.RWMutex
	lifecycleMu sync.Mutex
	rooms       map[int64]map[*Client]struct{}
	clients     map[*Client]struct{}
	users       map[int64]int
	limits      Limits
	incoming    []chan *redis.Message
	rdb         *redis.Client
	pubsub      *redis.PubSub
	ctx         context.Context
	cancel      context.CancelFunc
	wg          sync.WaitGroup
}

func New(rdb *redis.Client, options ...Limits) *Hub {
	limits := Limits{MaxClients: 10000, MaxClientsPerUser: 5}
	if len(options) > 0 {
		if options[0].MaxClients > 0 {
			limits.MaxClients = options[0].MaxClients
		}
		if options[0].MaxClientsPerUser > 0 {
			limits.MaxClientsPerUser = options[0].MaxClientsPerUser
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	h := &Hub{rooms: make(map[int64]map[*Client]struct{}), clients: make(map[*Client]struct{}),
		users: make(map[int64]int), limits: limits, incoming: make([]chan *redis.Message, broadcastWorkers),
		rdb: rdb, ctx: ctx, cancel: cancel}
	for i := range h.incoming {
		h.incoming[i] = make(chan *redis.Message, 512)
	}
	return h
}

// Run preserves Redis receive order within each channel by hashing rooms to
// one worker. Replicas ignore events for rooms with no local subscribers.
func (h *Hub) Run() {
	h.lifecycleMu.Lock()
	if h.ctx.Err() != nil {
		h.lifecycleMu.Unlock()
		return
	}
	h.pubsub = h.rdb.PSubscribe(h.ctx, PubSubPrefix+"*")
	for i := range h.incoming {
		h.wg.Add(1)
		go func(queue <-chan *redis.Message) {
			defer h.wg.Done()
			h.broadcastWorker(queue)
		}(h.incoming[i])
	}
	h.wg.Add(1)
	go func() {
		defer h.wg.Done()
		ch := h.pubsub.Channel(redis.WithChannelSize(4096))
		for {
			select {
			case <-h.ctx.Done():
				return
			case msg, ok := <-ch:
				if !ok {
					return
				}
				var id int64
				if !parseChannelID(msg.Channel, &id) || h.LocalCount(id) == 0 {
					continue
				}
				select {
				case h.incoming[id%int64(len(h.incoming))] <- msg:
				default:
					// Never silently leave a client with missing durable events.
					// Reconnect forces an authoritative HTTP history refresh.
					h.disconnectRoom(id)
					logger.Warnf("hub: queue saturated, reconnecting room=%d", id)
				}
			}
		}
	}()
	h.lifecycleMu.Unlock()
	<-h.ctx.Done()
}

func (h *Hub) Shutdown() {
	h.lifecycleMu.Lock()
	h.cancel()
	if h.pubsub != nil {
		_ = h.pubsub.Close()
	}
	h.lifecycleMu.Unlock()
	h.mu.RLock()
	clients := make([]*Client, 0, len(h.clients))
	for c := range h.clients {
		clients = append(clients, c)
	}
	h.mu.RUnlock()
	for _, c := range clients {
		h.removeClient(c)
	}
	h.wg.Wait()
}

func (h *Hub) Publish(ctx context.Context, channelID int64, event WSEvent) error {
	data, err := json.Marshal(event)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	return h.rdb.Publish(ctx, redisKey(channelID), data).Err()
}

// RegisterClient is synchronous: a connection is admitted and subscribed
// before its read/write pumps start. Duplicate removal is always safe.
func (h *Hub) CanAdmit(userID int64) bool {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return h.ctx.Err() == nil && len(h.clients) < h.limits.MaxClients && h.users[userID] < h.limits.MaxClientsPerUser
}

func (h *Hub) RegisterClient(c *Client) bool {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.ctx.Err() != nil {
		return false
	}
	if _, exists := h.clients[c]; exists {
		return true
	}
	if len(h.clients) >= h.limits.MaxClients || h.users[c.UserID] >= h.limits.MaxClientsPerUser {
		return false
	}
	h.clients[c] = struct{}{}
	h.users[c.UserID]++
	for _, id := range c.channelIDs {
		if h.rooms[id] == nil {
			h.rooms[id] = make(map[*Client]struct{})
		}
		h.rooms[id][c] = struct{}{}
	}
	return true
}

func (h *Hub) UnregisterClient(c *Client) { h.removeClient(c) }

// LocalCount returns the number of locally connected clients for a channel.
func (h *Hub) LocalCount(channelID int64) int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.rooms[channelID])
}

func presenceKey(userID int64) string { return "chat:presence:user:" + strconv.FormatInt(userID, 10) }

// TouchPresence is deliberately best-effort: chat delivery must never be
// blocked by a temporary Redis problem, and the existing pub/sub path will
// surface such a problem independently.
func (h *Hub) TouchPresence(userID int64) {
	if userID <= 0 {
		return
	}
	ctx, cancel := context.WithTimeout(h.ctx, 500*time.Millisecond)
	defer cancel()
	if err := h.rdb.Set(ctx, presenceKey(userID), "1", PresenceTTL).Err(); err != nil {
		logger.Warnf("hub: touch presence user=%d: %v", userID, err)
	}
}

func (h *Hub) IsOnline(ctx context.Context, userID int64) (bool, error) {
	if userID <= 0 {
		return false, nil
	}
	count, err := h.rdb.Exists(ctx, presenceKey(userID)).Result()
	return count > 0, err
}

// -------------------------------------------------------------------
// internal helpers
// -------------------------------------------------------------------

func (h *Hub) removeClient(c *Client) {
	h.mu.Lock()
	if _, exists := h.clients[c]; !exists {
		h.mu.Unlock()
		return
	}
	delete(h.clients, c)
	h.users[c.UserID]--
	if h.users[c.UserID] == 0 {
		delete(h.users, c.UserID)
	}
	for _, id := range c.channelIDs {
		if room := h.rooms[id]; room != nil {
			delete(room, c)
			if len(room) == 0 {
				delete(h.rooms, id)
			}
		}
	}
	h.mu.Unlock()
	c.close()
}

func (h *Hub) roomClients(id int64) []*Client {
	h.mu.RLock()
	defer h.mu.RUnlock()
	clients := make([]*Client, 0, len(h.rooms[id]))
	for c := range h.rooms[id] {
		clients = append(clients, c)
	}
	return clients
}

func (h *Hub) disconnectRoom(id int64) {
	for _, c := range h.roomClients(id) {
		h.removeClient(c)
	}
}

func (h *Hub) broadcastWorker(queue <-chan *redis.Message) {
	for {
		select {
		case <-h.ctx.Done():
			return
		case msg := <-queue:
			h.fanOut(msg)
		}
	}
}

func (h *Hub) fanOut(msg *redis.Message) {
	if msg == nil {
		return
	}
	var id int64
	if !parseChannelID(msg.Channel, &id) {
		return
	}
	var envelope struct {
		Type EventType `json:"type"`
	}
	if json.Unmarshal([]byte(msg.Payload), &envelope) == nil && envelope.Type == EventAccessChanged {
		h.disconnectRoom(id)
		return
	}
	data := []byte(msg.Payload)
	for _, c := range h.roomClients(id) {
		if !c.enqueue(data) {
			h.removeClient(c)
		}
	}
}

func redisKey(channelID int64) string {
	return PubSubPrefix + int64ToString(channelID)
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
	if len(key) <= len(PubSubPrefix) || key[:len(PubSubPrefix)] != PubSubPrefix {
		return false
	}
	n, err := strconv.ParseInt(key[len(PubSubPrefix):], 10, 64)
	if err != nil || n <= 0 {
		return false
	}
	*out = n
	return true
}

// UnregisterChannel forces local membership revalidation after administration.
func (h *Hub) UnregisterChannel(id int64) { h.disconnectRoom(id) }

// OnlineUsers batches presence into one Redis round-trip rather than one per member.
func (h *Hub) OnlineUsers(ctx context.Context, ids []int64) (map[int64]bool, error) {
	result := make(map[int64]bool, len(ids))
	if len(ids) == 0 {
		return result, nil
	}
	keys := make([]string, len(ids))
	for i, id := range ids {
		keys[i] = presenceKey(id)
	}
	values, err := h.rdb.MGet(ctx, keys...).Result()
	if err != nil {
		return nil, err
	}
	for i, value := range values {
		result[ids[i]] = value != nil
	}
	return result, nil
}
