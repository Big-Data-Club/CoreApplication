package handler

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"chat-service/internal/dto"
	"chat-service/internal/middleware"
	"chat-service/internal/repository"
	"chat-service/pkg/hub"
	"chat-service/pkg/logger"
	"chat-service/pkg/storage"

	"github.com/gin-gonic/gin"
)

// ChatHandler handles REST and WebSocket chat endpoints.
type ChatHandler struct {
	chatRepo *repository.ChatRepository
	userRepo *repository.UserRepository
	hub      *hub.Hub
	store    *storage.ObjectStore
	jwtSecret string
}

func NewChatHandler(
	chatRepo *repository.ChatRepository,
	userRepo *repository.UserRepository,
	h *hub.Hub,
	store *storage.ObjectStore,
	jwtSecret string,
) *ChatHandler {
	return &ChatHandler{
		chatRepo:  chatRepo,
		userRepo:  userRepo,
		hub:       h,
		store:     store,
		jwtSecret: jwtSecret,
	}
}

const maxAttachmentBytes int64 = 20 * 1024 * 1024

var allowedAttachmentTypes = map[string]string{
	".pdf":  "application/pdf",
	".doc":  "application/msword",
	".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	".ppt":  "application/vnd.ms-powerpoint",
	".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
	".xls":  "application/vnd.ms-excel",
	".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	".csv":  "text/csv",
	".txt":  "text/plain",
	".zip":  "application/zip",
	".jpg":  "image/jpeg",
	".jpeg": "image/jpeg",
	".png":  "image/png",
	".gif":  "image/gif",
	".webp": "image/webp",
	".mp3":  "audio/mpeg",
	".wav":  "audio/wav",
	".m4a":  "audio/mp4",
	".mp4":  "video/mp4",
	".webm": "video/webm",
}

// ─── ListChannels GET /api/v1/chat/channels ───────────────────────────────────

func (h *ChatHandler) ListChannels(c *gin.Context) {
	userID := mustUserID(c)
	roles := mustRoles(c)

	channels, err := h.chatRepo.ListAccessibleChannels(c.Request.Context(), userID, roles)
	if err != nil {
		logger.Errorf("list channels user=%d: %v", userID, err)
		c.JSON(dto.ErrInternal("Failed to load channels"))
		return
	}

	// Collect DM channel IDs
	var dmChannelIDs []int64
	for _, ch := range channels {
		if ch.IsDM {
			dmChannelIDs = append(dmChannelIDs, ch.ID)
		}
	}

	// Batch fetch DM participants
	dmUsers := make(map[int64]repository.User)
	if len(dmChannelIDs) > 0 {
		var err error
		dmUsers, err = h.chatRepo.GetDMParticipants(c.Request.Context(), dmChannelIDs, userID)
		if err != nil {
			logger.Errorf("get dm participants user=%d: %v", userID, err)
			c.JSON(dto.ErrInternal("Failed to load participants"))
			return
		}
	}

	resp := make([]dto.ChannelResponse, len(channels))
	for i, ch := range channels {
		dtoCh := channelToDTO(ch)
		if ch.IsDM {
			if u, ok := dmUsers[ch.ID]; ok {
				dtoCh.DMUser = &dto.UserResponse{
					ID:             u.ID,
					Email:          u.Email,
					FullName:       u.FullName,
					ProfilePicture: u.ProfilePicture,
				}
			}
		}
		resp[i] = dtoCh
	}
	c.JSON(dto.OK(resp))
}

// ─── SearchUsers GET /api/v1/chat/users/search ─────────────────────────────────

func (h *ChatHandler) SearchUsers(c *gin.Context) {
	userID := mustUserID(c)
	query := c.Query("q")

	users, err := h.userRepo.SearchUsers(c.Request.Context(), query, userID, 15)
	if err != nil {
		logger.Errorf("search users query=%q caller=%d: %v", query, userID, err)
		c.JSON(dto.ErrInternal("Failed to search users"))
		return
	}

	resp := make([]dto.UserResponse, len(users))
	for i, u := range users {
		resp[i] = dto.UserResponse{
			ID:             u.ID,
			Email:          u.Email,
			FullName:       u.FullName,
			ProfilePicture: u.ProfilePicture,
		}
	}
	c.JSON(dto.OK(resp))
}

// ─── GetOrCreateDM POST /api/v1/chat/dm ────────────────────────────────────────

func (h *ChatHandler) GetOrCreateDM(c *gin.Context) {
	userID := mustUserID(c)

	var req dto.CreateDMRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest("Missing or invalid user_id"))
		return
	}

	if req.UserID == userID {
		c.JSON(dto.ErrBadRequest("You cannot start a direct message with yourself"))
		return
	}

	// Verify target user exists
	targetUser, err := h.userRepo.GetByID(c.Request.Context(), req.UserID)
	if err != nil {
		logger.Errorf("lookup target user %d: %v", req.UserID, err)
		c.JSON(dto.ErrInternal("Failed to verify user"))
		return
	}
	if targetUser == nil {
		c.JSON(dto.ErrNotFound("Target user not found"))
		return
	}

	// Ensure caller exists in chat DB (may not have been synced yet)
	callerEmail := c.GetString("user_email")
	if err := h.userRepo.EnsureGuestUser(c.Request.Context(), userID, callerEmail); err != nil {
		logger.Warnf("get/create dm ensure guest user for caller %d: %v", userID, err)
	}

	ch, err := h.chatRepo.GetOrCreateDMChannel(c.Request.Context(), userID, req.UserID)
	if err != nil {
		logger.Errorf("get/create dm channel caller=%d target=%d: %v", userID, req.UserID, err)
		c.JSON(dto.ErrInternal("Failed to initialize direct message"))
		return
	}

	resp := channelToDTO(*ch)
	resp.DMUser = &dto.UserResponse{
		ID:             targetUser.ID,
		Email:          targetUser.Email,
		FullName:       targetUser.FullName,
		ProfilePicture: targetUser.ProfilePicture,
	}

	c.JSON(dto.Created(resp))
}

// ─── ListMessages GET /api/v1/chat/channels/:id/messages ─────────────────────

func (h *ChatHandler) ListMessages(c *gin.Context) {
	channelID, ok := parseID(c, "id")
	if !ok {
		return
	}

	userID := mustUserID(c)
	roles := mustRoles(c)

	// Access check
	canRead, _, err := h.chatRepo.CanUserAccess(c.Request.Context(), channelID, userID, roles)
	if err != nil {
		logger.Errorf("access check channel=%d user=%d: %v", channelID, userID, err)
		c.JSON(dto.ErrInternal("Access check failed"))
		return
	}
	if !canRead {
		c.JSON(dto.ErrForbidden("You do not have access to this channel"))
		return
	}

	// Cursor pagination: ?before_id=<msgID>&limit=<n>
	beforeID := int64(0)
	if s := c.Query("before_id"); s != "" {
		if v, err := strconv.ParseInt(s, 10, 64); err == nil {
			beforeID = v
		}
	}
	limit := 50
	if s := c.Query("limit"); s != "" {
		if v, _ := strconv.Atoi(s); v > 0 && v <= 100 {
			limit = v
		}
	}

	msgs, err := h.chatRepo.ListMessages(c.Request.Context(), channelID, beforeID, limit)
	if err != nil {
		logger.Errorf("list messages channel=%d: %v", channelID, err)
		c.JSON(dto.ErrInternal("Failed to load messages"))
		return
	}

	// Determine next cursor
	var nextCursor int64
	hasMore := len(msgs) == limit
	if hasMore && len(msgs) > 0 {
		nextCursor = msgs[0].ID // oldest ID in the current page = cursor for next page
	}

	resp := make([]dto.MessageResponse, len(msgs))
	for i, m := range msgs {
		resp[i] = messageToDTO(m)
	}

	c.JSON(dto.OK(dto.MessageListResponse{
		Messages:   resp,
		NextCursor: nextCursor,
		HasMore:    hasMore,
	}))
}

// ─── SendMessage POST /api/v1/chat/channels/:id/messages ─────────────────────
// REST fallback for environments where WebSocket is unavailable.

func (h *ChatHandler) SendMessage(c *gin.Context) {
	channelID, ok := parseID(c, "id")
	if !ok {
		return
	}

	userID := mustUserID(c)
	email := c.GetString("user_email")
	roles := mustRoles(c)

	// Access check
	canRead, canWrite, err := h.chatRepo.CanUserAccess(c.Request.Context(), channelID, userID, roles)
	if err != nil || !canRead || !canWrite {
		c.JSON(dto.ErrForbidden("Cannot write to this channel"))
		return
	}

	var req dto.SendMessageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	// Ensure user exists in chat DB (may not have been synced yet)
	if err := h.userRepo.EnsureGuestUser(c.Request.Context(), userID, email); err != nil {
		logger.Warnf("ensure guest user %d: %v", userID, err)
	}

	msg, err := h.chatRepo.CreateMessage(c.Request.Context(), channelID, userID, req.Body, req.ParentID)
	if err != nil {
		logger.Errorf("create message channel=%d user=%d: %v", channelID, userID, err)
		c.JSON(dto.ErrInternal("Failed to send message"))
		return
	}

	// Publish to Redis so WebSocket clients on all replicas receive it
	event := hub.WSEvent{
		Type:      hub.EventMessage,
		ChannelID: channelID,
		Payload:   messagepayload(msg),
		Timestamp: time.Now().UTC(),
	}
	if err := h.hub.Publish(c.Request.Context(), channelID, event); err != nil {
		logger.Warnf("publish message: %v", err)
	}

	c.JSON(dto.Created(messageToDTO(*msg)))
}

// UploadAttachment streams one attachment (up to 20 MiB) into object storage,
// creates its message atomically with metadata, and broadcasts the normal
// message event. Files never pass through the frontend filesystem or a public
// static URL.
func (h *ChatHandler) UploadAttachment(c *gin.Context) {
	channelID, ok := parseID(c, "id")
	if !ok {
		return
	}
	if h.store == nil {
		c.JSON(http.StatusServiceUnavailable, dto.APIResponse{Success: false, Error: &dto.APIError{Code: "storage_unavailable", Message: "File attachments are temporarily unavailable"}})
		return
	}
	userID := mustUserID(c)
	roles := mustRoles(c)
	_, canWrite, err := h.chatRepo.CanUserAccess(c.Request.Context(), channelID, userID, roles)
	if err != nil || !canWrite {
		c.JSON(dto.ErrForbidden("Cannot upload to this channel"))
		return
	}

	// The extra KiB allows multipart boundaries while retaining a strict 20 MiB
	// file cap. MaxBytesReader aborts a malicious oversized stream before it can
	// consume pod memory or disk.
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxAttachmentBytes+1024*1024)
	reader, err := c.Request.MultipartReader()
	if err != nil {
		c.JSON(dto.ErrBadRequest("Expected multipart/form-data"))
		return
	}

	var (
		body     string
		parentID *int64
		stored   *repository.Attachment
	)
	cleanupStored := func() {
		if stored != nil {
			_ = h.store.Delete(c.Request.Context(), stored.ObjectKey)
		}
	}
	for {
		part, nextErr := reader.NextPart()
		if nextErr == io.EOF {
			break
		}
		if nextErr != nil {
			cleanupStored()
			c.JSON(dto.ErrBadRequest("Could not read uploaded file"))
			return
		}
		name := part.FormName()
		switch name {
		case "body":
			value, readErr := io.ReadAll(io.LimitReader(part, 4001))
			_ = part.Close()
			if readErr != nil || len(value) > 4000 {
				cleanupStored()
				c.JSON(dto.ErrBadRequest("Attachment caption must be at most 4000 characters"))
				return
			}
			body = strings.TrimSpace(string(value))
		case "parent_id":
			value, readErr := io.ReadAll(io.LimitReader(part, 32))
			_ = part.Close()
			if readErr != nil || len(value) == 0 { continue }
			id, parseErr := strconv.ParseInt(string(value), 10, 64)
			if parseErr != nil || id <= 0 {
				cleanupStored()
				c.JSON(dto.ErrBadRequest("Invalid parent_id"))
				return
			}
			parentID = &id
		case "file":
			if stored != nil {
				_ = part.Close()
				cleanupStored()
				c.JSON(dto.ErrBadRequest("Only one attachment is allowed per message"))
				return
			}
			fileName := strings.TrimSpace(filepath.Base(part.FileName()))
			ext := strings.ToLower(filepath.Ext(fileName))
			contentType, allowed := allowedAttachmentTypes[ext]
			if !allowed || fileName == "." || fileName == "" {
				_ = part.Close()
				cleanupStored()
				c.JSON(dto.ErrBadRequest("Unsupported file type"))
				return
			}
			prefix := make([]byte, 512)
			n, readErr := io.ReadFull(part, prefix)
			if readErr != nil && readErr != io.ErrUnexpectedEOF && readErr != io.EOF {
				_ = part.Close()
				cleanupStored()
				c.JSON(dto.ErrBadRequest("Could not read uploaded file"))
				return
			}
			prefix = prefix[:n]
			if n == 0 {
				_ = part.Close()
				cleanupStored()
				c.JSON(dto.ErrBadRequest("Empty files are not allowed"))
				return
			}
			// The extension allowlist is authoritative. Sniffing rejects HTML
			// disguised as a high-risk executable image/document upload.
			sniffed := http.DetectContentType(prefix)
			if strings.HasPrefix(sniffed, "text/html") || strings.HasPrefix(sniffed, "application/x-msdownload") {
				_ = part.Close()
				cleanupStored()
				c.JSON(dto.ErrBadRequest("Unsafe file content"))
				return
			}
			attachmentID, idErr := randomID()
			if idErr != nil {
				_ = part.Close()
				cleanupStored()
				c.JSON(dto.ErrInternal("Could not initialize attachment"))
				return
			}
			objectKey := fmt.Sprintf("chat/%s%s", attachmentID, ext)
			size, putErr := h.store.Put(c.Request.Context(), objectKey, io.MultiReader(bytes.NewReader(prefix), part), contentType)
			_ = part.Close()
			if putErr != nil || size <= 0 || size > maxAttachmentBytes {
				_ = h.store.Delete(c.Request.Context(), objectKey)
				if size > maxAttachmentBytes {
					c.JSON(dto.ErrBadRequest("File exceeds the 20MB limit"))
				} else {
					logger.Warnf("attachment upload channel=%d user=%d: %v", channelID, userID, putErr)
					c.JSON(dto.ErrInternal("Failed to store attachment"))
				}
				return
			}
			stored = &repository.Attachment{ID: attachmentID, ObjectKey: objectKey, FileName: fileName, MimeType: contentType, SizeBytes: size}
		default:
			_ = part.Close()
		}
	}

	if stored == nil {
		c.JSON(dto.ErrBadRequest("No attachment was provided"))
		return
	}
	// Ensure a transient user can send attachments exactly as with text messages.
	if err := h.userRepo.EnsureGuestUser(c.Request.Context(), userID, c.GetString("user_email")); err != nil {
		logger.Warnf("ensure attachment sender user=%d: %v", userID, err)
	}
	msg, err := h.chatRepo.CreateMessageWithAttachment(c.Request.Context(), channelID, userID, body, parentID, *stored)
	if err != nil {
		_ = h.store.Delete(c.Request.Context(), stored.ObjectKey)
		logger.Errorf("create attachment message channel=%d user=%d: %v", channelID, userID, err)
		c.JSON(dto.ErrInternal("Failed to create attachment message"))
		return
	}
	event := hub.WSEvent{Type: hub.EventMessage, ChannelID: channelID, Payload: messagepayload(msg), Timestamp: time.Now().UTC()}
	if err := h.hub.Publish(c.Request.Context(), channelID, event); err != nil {
		logger.Warnf("publish attachment message: %v", err)
	}
	c.JSON(dto.Created(messageToDTO(*msg)))
}

// DownloadAttachment serves an object only after verifying current channel
// membership. This check also prevents an old copied URL from accessing a
// deleted message.
func (h *ChatHandler) DownloadAttachment(c *gin.Context) {
	if h.store == nil {
		c.JSON(http.StatusServiceUnavailable, dto.APIResponse{Success: false, Error: &dto.APIError{Code: "storage_unavailable", Message: "File attachments are temporarily unavailable"}})
		return
	}
	attachmentID := c.Param("attachmentId")
	if attachmentID == "" || len(attachmentID) > 64 {
		c.JSON(dto.ErrBadRequest("Invalid attachment id"))
		return
	}
	attachment, channelID, isDeleted, err := h.chatRepo.GetAttachment(c.Request.Context(), attachmentID)
	if err != nil {
		logger.Errorf("get attachment %s: %v", attachmentID, err)
		c.JSON(dto.ErrInternal("Failed to load attachment"))
		return
	}
	if attachment == nil || isDeleted {
		c.JSON(dto.ErrNotFound("Attachment not found"))
		return
	}
	canRead, _, err := h.chatRepo.CanUserAccess(c.Request.Context(), channelID, mustUserID(c), mustRoles(c))
	if err != nil || !canRead {
		c.JSON(dto.ErrForbidden("You do not have access to this attachment"))
		return
	}
	object, err := h.store.Get(c.Request.Context(), attachment.ObjectKey)
	if err != nil {
		logger.Warnf("open attachment id=%s: %v", attachmentID, err)
		c.JSON(dto.ErrNotFound("Attachment not found"))
		return
	}
	defer object.Body.Close()
	c.Header("X-Content-Type-Options", "nosniff")
	c.Header("Cache-Control", "private, max-age=300")
	c.Header("Content-Type", attachment.MimeType)
	fileName := strings.ReplaceAll(attachment.FileName, `"`, "")
	if c.Query("download") == "1" || !isInlineAttachment(attachment.MimeType) {
		c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, fileName))
	} else {
		c.Header("Content-Disposition", fmt.Sprintf(`inline; filename="%s"`, fileName))
	}
	http.ServeContent(c.Writer, c.Request, fileName, object.ModifiedAt, object.Body)
}

func isInlineAttachment(contentType string) bool {
	return strings.HasPrefix(contentType, "image/") || contentType == "application/pdf"
}

func randomID() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}

// ─── DeleteMessage DELETE /api/v1/chat/channels/:id/messages/:msgId ──────────

func (h *ChatHandler) DeleteMessage(c *gin.Context) {
	channelID, ok := parseID(c, "id")
	if !ok {
		return
	}
	msgID, ok := parseID(c, "msgId")
	if !ok {
		return
	}

	userID := mustUserID(c)
	roles := mustRoles(c)
	isAdmin := hasRole(roles, "ADMIN")

	// Non-admin must have write access to this channel
	if !isAdmin {
		_, canWrite, err := h.chatRepo.CanUserAccess(c.Request.Context(), channelID, userID, roles)
		if err != nil || !canWrite {
			c.JSON(dto.ErrForbidden("Cannot delete in this channel"))
			return
		}
	}

	if err := h.chatRepo.SoftDeleteMessage(c.Request.Context(), msgID, userID, isAdmin); err != nil {
		c.JSON(dto.ErrForbidden(err.Error()))
		return
	}

	// Broadcast delete event
	event := hub.WSEvent{
		Type:      hub.EventDelete,
		ChannelID: channelID,
		Payload:   hub.MessagePayload{ID: msgID, IsDeleted: true},
		Timestamp: time.Now().UTC(),
	}
	_ = h.hub.Publish(c.Request.Context(), channelID, event)

	c.JSON(dto.OK(gin.H{"deleted": true}))
}

// ─── EditMessage PUT /api/v1/chat/channels/:id/messages/:msgId ────────────────

func (h *ChatHandler) EditMessage(c *gin.Context) {
	channelID, ok := parseID(c, "id")
	if !ok {
		return
	}
	msgID, ok := parseID(c, "msgId")
	if !ok {
		return
	}

	userID := mustUserID(c)

	var req dto.EditMessageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	msg, err := h.chatRepo.UpdateMessageBody(c.Request.Context(), msgID, userID, req.Body)
	if err != nil {
		logger.Errorf("edit message msgID=%d user=%d: %v", msgID, userID, err)
		c.JSON(dto.ErrForbidden(err.Error()))
		return
	}

	// Broadcast edit event so all clients update in-place without reload
	event := hub.WSEvent{
		Type:      hub.EventEdit,
		ChannelID: channelID,
		Payload:   messagepayload(msg),
		Timestamp: time.Now().UTC(),
	}
	_ = h.hub.Publish(c.Request.Context(), channelID, event)

	c.JSON(dto.OK(messageToDTO(*msg)))
}

// ─── WebSocket GET /api/v1/chat/ws?token=<jwt> ────────────────────────────────

func (h *ChatHandler) ServeWS(c *gin.Context) {
	// 1. Authenticate via JWT in query param (browsers can't set headers on WS)
	claims, ok := middleware.ParseTokenFromQuery(c, h.jwtSecret)
	if !ok {
		return
	}

	userID := claims.UserID
	email := claims.Email
	roles := middleware.ExportNormalizeRoles(claims.Roles)

	// 2. Ensure user exists in chat DB
	ctx := context.Background()
	if err := h.userRepo.EnsureGuestUser(ctx, userID, email); err != nil {
		logger.Warnf("ws ensure guest user %d: %v", userID, err)
	}

	// 3. Determine which channels this user can access
	channels, err := h.chatRepo.ListAccessibleChannels(ctx, userID, roles)
	if err != nil {
		logger.Errorf("ws list channels user=%d: %v", userID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to load channels"})
		return
	}

	channelIDs := make([]int64, len(channels))
	for i, ch := range channels {
		channelIDs[i] = ch.ID
	}

	if len(channelIDs) == 0 {
		c.JSON(http.StatusForbidden, gin.H{"error": "No accessible channels"})
		return
	}

	// 4. Upgrade to WebSocket
	conn, err := hub.Upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		logger.Warnf("ws upgrade user=%d ip=%s: %v", userID, c.ClientIP(), err)
		return
	}

	// 5. Create client and register with hub
	client := hub.NewClient(h.hub, conn, userID, email, roles, channelIDs)
	h.hub.RegisterClient(client)

	logger.Infof("ws: user=%d ip=%s channels=%v roles=%v", userID, c.ClientIP(), channelIDs, roles)

	// 6. Start read/write pumps (each in its own goroutine)
	go client.WritePump()
	go client.ReadPump(func(c *hub.Client, msg hub.InboundMsg) {
		h.handleWSMessage(ctx, c, msg)
	})
}

// handleWSMessage processes an inbound WebSocket frame from a client.
func (h *ChatHandler) handleWSMessage(ctx context.Context, c *hub.Client, msg hub.InboundMsg) {
	switch msg.Type {
	case hub.EventMessage:
		if msg.Body == "" || len(msg.Body) > 4000 {
			return
		}

		// Access check (authoritative - re-check even though client is registered)
		_, canWrite, err := h.chatRepo.CanUserAccess(ctx, msg.ChannelID, c.UserID, c.Roles)
		if err != nil || !canWrite {
			return
		}

		// Persist
		t0 := time.Now()
		newMsg, err := h.chatRepo.CreateMessage(ctx, msg.ChannelID, c.UserID, msg.Body, msg.ParentID)
		if err != nil {
			logger.Errorf("ws: persist message channelID=%d userID=%d: %v", msg.ChannelID, c.UserID, err)
			return
		}
		logger.Debugf("ws: message persisted msgID=%d channelID=%d latency=%dms",
			newMsg.ID, msg.ChannelID, time.Since(t0).Milliseconds())

		// Publish to Redis (all replicas fan-out to their local clients)
		event := hub.WSEvent{
			Type:      hub.EventMessage,
			ChannelID: msg.ChannelID,
			Payload:   messagepayload(newMsg),
			Timestamp: time.Now().UTC(),
		}
		if err := h.hub.Publish(ctx, msg.ChannelID, event); err != nil {
			logger.Warnf("ws publish: %v", err)
		}

	case hub.EventTyping:
		// Publish ephemeral typing indicator (not persisted)
		event := hub.WSEvent{
			Type:      hub.EventTyping,
			ChannelID: msg.ChannelID,
			Payload: hub.TypingPayload{
				UserID:   c.UserID,
				UserName: c.Email,
			},
			Timestamp: time.Now().UTC(),
		}
		_ = h.hub.Publish(ctx, msg.ChannelID, event)

	case hub.EventPing:
		// Client-initiated keepalive ping - no-op (pong is handled at WS layer)
	}
}

// ── helpers ──────────────────────────────────────────────────────────────────

func mustUserID(c *gin.Context) int64 {
	v, _ := c.Get("user_id")
	id, _ := v.(int64)
	return id
}

func mustRoles(c *gin.Context) []string {
	v, _ := c.Get("user_roles")
	roles, _ := v.([]string)
	return roles
}

func hasRole(roles []string, role string) bool {
	for _, r := range roles {
		if r == role {
			return true
		}
	}
	return false
}

func parseID(c *gin.Context, param string) (int64, bool) {
	s := c.Param(param)
	id, err := strconv.ParseInt(s, 10, 64)
	if err != nil || id <= 0 {
		c.JSON(dto.ErrBadRequest(fmt.Sprintf("invalid %s", param)))
		return 0, false
	}
	return id, true
}

func channelToDTO(ch repository.Channel) dto.ChannelResponse {
	return dto.ChannelResponse{
		ID:          ch.ID,
		Slug:        ch.Slug,
		Name:        ch.Name,
		Description: ch.Description,
		IsPrivate:   ch.IsPrivate,
		IsDM:        ch.IsDM,
		CreatedAt:   ch.CreatedAt,
	}
}

func messageToDTO(m repository.Message) dto.MessageResponse {
	response := dto.MessageResponse{
		ID:               m.ID,
		ChannelID:        m.ChannelID,
		SenderID:         m.SenderID,
		SenderName:       m.SenderName,
		SenderEmail:      m.SenderEmail,
		SenderAvatar:     m.SenderAvatar,
		Body:             m.Body,
		IsDeleted:        m.IsDeleted,
		IsEdited:         m.IsEdited,
		ParentID:         m.ParentID,
		ParentSenderName: m.ParentSenderName,
		ParentBody:       m.ParentBody,
		CreatedAt:        m.CreatedAt,
	}
	if len(m.Attachments) > 0 {
		response.Attachments = make([]dto.AttachmentResponse, len(m.Attachments))
		for i, attachment := range m.Attachments {
			response.Attachments[i] = dto.AttachmentResponse{ID: attachment.ID, FileName: attachment.FileName, MimeType: attachment.MimeType, SizeBytes: attachment.SizeBytes, CreatedAt: attachment.CreatedAt}
		}
	}
	return response
}

// messagepayload builds a hub.MessagePayload from a repository.Message.
// Used for both new messages and edit broadcasts.
func messagepayload(m *repository.Message) hub.MessagePayload {
	p := hub.MessagePayload{
		ID:           m.ID,
		SenderID:     m.SenderID,
		SenderName:   m.SenderName,
		SenderAvatar: m.SenderAvatar,
		Body:         m.Body,
		IsEdited:     m.IsEdited,
	}
	if m.ParentID != nil {
		p.ParentID = m.ParentID
		p.ParentSenderName = m.ParentSenderName
		p.ParentBody = m.ParentBody
	}
	if len(m.Attachments) > 0 {
		p.Attachments = make([]hub.AttachmentPayload, len(m.Attachments))
		for i, attachment := range m.Attachments {
			p.Attachments[i] = hub.AttachmentPayload{ID: attachment.ID, FileName: attachment.FileName, MimeType: attachment.MimeType, SizeBytes: attachment.SizeBytes, CreatedAt: attachment.CreatedAt}
		}
	}
	return p
}
