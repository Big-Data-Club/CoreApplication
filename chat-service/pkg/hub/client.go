package hub

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"chat-service/pkg/logger"

	"github.com/gorilla/websocket"
)

// Client represents a single WebSocket connection.
// Each Client runs two goroutines:
//
//	readPump  – reads frames from the WS connection, publishes to Redis.
//	writePump – drains the send channel and writes frames to the WS connection.
//
// This is the standard gorilla/websocket pattern. The send channel is buffered
// (ClientSendBuffer) so the broadcast loop never blocks on a slow client.
type Client struct {
	hub *Hub

	conn *websocket.Conn

	// send is the outbound message queue. Closed by the hub when the client is
	// unregistered. The writePump exits on channel close.
	send chan []byte

	// UserID is set from the validated JWT and used for permission checks.
	UserID int64

	// Email is the user's email extracted from JWT.
	Email string

	// Roles holds the JWT roles (e.g. ["ADMIN", "TEACHER"]).
	Roles []string

	// channelIDs is the set of channels this connection is subscribed to.
	channelIDs []int64

	// publishFn is called by readPump to publish outbound events.
	// Injected so that tests can replace it without a real Redis client.
	publishFn func(channelID int64, event WSEvent) error
}

// NewClient constructs a Client and registers it with the hub.
func NewClient(
	h *Hub,
	conn *websocket.Conn,
	userID int64,
	email string,
	roles []string,
	channelIDs []int64,
) *Client {
	c := &Client{
		hub:        h,
		conn:       conn,
		send:       make(chan []byte, ClientSendBuffer),
		UserID:     userID,
		Email:      email,
		Roles:      roles,
		channelIDs: channelIDs,
	}
	c.publishFn = func(channelID int64, event WSEvent) error {
		return h.Publish(context.Background(), channelID, event)
	}
	return c
}

// InboundMsg is the client-side JSON frame sent TO the server.
type InboundMsg struct {
	Type      EventType `json:"type"`
	ChannelID int64     `json:"channel_id"`
	Body      string    `json:"body,omitempty"` // for EventMessage
}

// WritePump pumps messages from the send channel to the WebSocket.
// One goroutine per client.
func (c *Client) WritePump() {
	ticker := time.NewTicker(PingPeriod)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case msg, ok := <-c.send:
			_ = c.conn.SetWriteDeadline(time.Now().Add(WriteWait))
			if !ok {
				// Hub closed the channel — send close frame.
				_ = c.conn.WriteMessage(websocket.CloseMessage,
					websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
				return
			}
			w, err := c.conn.NextWriter(websocket.TextMessage)
			if err != nil {
				return
			}
			if _, err := w.Write(msg); err != nil {
				return
			}
			// Flush any remaining queued messages in this write batch.
			n := len(c.send)
			for i := 0; i < n; i++ {
				if _, err := w.Write([]byte("\n")); err != nil {
					return
				}
				if _, err := w.Write(<-c.send); err != nil {
					return
				}
			}
			if err := w.Close(); err != nil {
				return
			}

		case <-ticker.C:
			_ = c.conn.SetWriteDeadline(time.Now().Add(WriteWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// ReadPump pumps messages from the WebSocket to the hub.
// One goroutine per client.
func (c *Client) ReadPump(onMessage func(client *Client, msg InboundMsg)) {
	defer func() {
		c.hub.UnregisterClient(c)
		c.conn.Close()
	}()

	c.conn.SetReadLimit(MaxMessageSize)
	_ = c.conn.SetReadDeadline(time.Now().Add(PongWait))
	c.conn.SetPongHandler(func(string) error {
		_ = c.conn.SetReadDeadline(time.Now().Add(PongWait))
		return nil
	})

	for {
		_, raw, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(
				err,
				websocket.CloseGoingAway,
				websocket.CloseAbnormalClosure,
				websocket.CloseNormalClosure,
			) {
				logger.Warnf("client %d: unexpected close: %v", c.UserID, err)
			}
			return
		}

		var msg InboundMsg
		if err := json.Unmarshal(raw, &msg); err != nil {
			// Malformed frame — skip, do not disconnect
			continue
		}

		// Validate the client is subscribed to the target channel
		if !c.subscribedTo(msg.ChannelID) {
			continue
		}

		onMessage(c, msg)
	}
}

func (c *Client) subscribedTo(channelID int64) bool {
	for _, id := range c.channelIDs {
		if id == channelID {
			return true
		}
	}
	return false
}

// Upgrader is a gorilla WebSocket upgrader with sensible defaults.
// CheckOrigin is intentionally left permissive here; CORS enforcement
// is handled at the Gin middleware layer before the upgrade.
var Upgrader = websocket.Upgrader{
	ReadBufferSize:  4 * 1024,
	WriteBufferSize: 4 * 1024,
	CheckOrigin: func(r *http.Request) bool {
		// Origin validation is done in the CORS middleware before we get here.
		return true
	},
}
