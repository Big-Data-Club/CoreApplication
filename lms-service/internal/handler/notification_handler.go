package handler

import (
	"context"
	"net/http"
	"time"

	"example/hello/internal/service"
	"example/hello/pkg/cache"
	"github.com/gin-gonic/gin"
)

type notificationStore interface {
	Feed(context.Context, int64) (*service.NotificationFeed, error)
	MarkRead(context.Context, int64, []string) error
	Channels(context.Context, int64) ([]string, error)
}
type NotificationHandler struct {
	store notificationStore
	cache *cache.RedisCache
}

func NewNotificationHandler(store notificationStore, redis *cache.RedisCache) *NotificationHandler {
	return &NotificationHandler{store: store, cache: redis}
}

func (h *NotificationHandler) List(c *gin.Context) {
	userID := c.GetInt64("user_id")
	if userID <= 0 {
		c.AbortWithStatus(http.StatusUnauthorized)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
	defer cancel()
	feed, err := h.store.Feed(ctx, userID)
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Thông báo tạm thời chưa sẵn sàng"})
		return
	}
	c.Header("Cache-Control", "no-store")
	c.JSON(http.StatusOK, feed)
}

func (h *NotificationHandler) Read(c *gin.Context) {
	userID := c.GetInt64("user_id")
	if userID <= 0 {
		c.AbortWithStatus(http.StatusUnauthorized)
		return
	}
	var body struct {
		Keys []string `json:"keys"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || !service.ValidNoticeKeys(body.Keys) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid notification keys"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 2*time.Second)
	defer cancel()
	if err := h.store.MarkRead(ctx, userID, body.Keys); err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Không thể lưu trạng thái đã đọc"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *NotificationHandler) Stream(c *gin.Context) {
	userID := c.GetInt64("user_id")
	if userID <= 0 {
		c.AbortWithStatus(http.StatusUnauthorized)
		return
	}
	// Reconnect periodically to revalidate JWT and current enrollment/membership.
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Minute)
	defer cancel()
	channels, err := h.store.Channels(ctx, userID)
	if err != nil {
		c.Status(http.StatusServiceUnavailable)
		return
	}
	subscribeCtx, stop := context.WithTimeout(ctx, 3*time.Second)
	subscription, err := h.cache.Subscribe(subscribeCtx, channels...)
	stop()
	if err != nil {
		c.Status(http.StatusServiceUnavailable)
		return
	}
	defer subscription.Close()
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache, no-transform")
	c.Header("X-Accel-Buffering", "no")
	// Subscribe before initial refresh; a reconnect always recovers missed hints.
	c.SSEvent("refresh", "refresh")
	c.Writer.Flush()
	heartbeat := time.NewTicker(20 * time.Second)
	defer heartbeat.Stop()
	messages := subscription.Channel()
	for {
		select {
		case <-ctx.Done():
			return
		case _, ok := <-messages:
			if !ok {
				return
			}
			c.SSEvent("refresh", "refresh")
			c.Writer.Flush()
		case <-heartbeat.C:
			c.Writer.WriteString(": heartbeat\n\n")
			c.Writer.Flush()
		}
	}
}
