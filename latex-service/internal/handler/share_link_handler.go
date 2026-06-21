package handler

import (
	"net/http"
	"strconv"

	"latex-service/internal/dto"
	"latex-service/internal/service"

	"github.com/gin-gonic/gin"
)

// ShareLinkHandler handles share link endpoints
type ShareLinkHandler struct {
	shareLinkService *service.ShareLinkService
}

// NewShareLinkHandler creates a new ShareLinkHandler
func NewShareLinkHandler(shareLinkService *service.ShareLinkService) *ShareLinkHandler {
	return &ShareLinkHandler{shareLinkService: shareLinkService}
}

// Create handles POST /projects/:id/share-links
func (h *ShareLinkHandler) Create(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	var req dto.CreateShareLinkRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	result, err := h.shareLinkService.CreateLink(c.Request.Context(), projectID, userID, &req)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("create_link_failed", err.Error()))
		return
	}
	c.JSON(http.StatusCreated, dto.NewDataResponse(result))
}

// List handles GET /projects/:id/share-links
func (h *ShareLinkHandler) List(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	result, err := h.shareLinkService.ListLinks(c.Request.Context(), projectID, userID)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("access_denied", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// Deactivate handles DELETE /projects/:id/share-links/:linkId
func (h *ShareLinkHandler) Deactivate(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	linkIDStr := c.Param("linkId")
	linkID, err := strconv.ParseInt(linkIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid link ID"))
		return
	}

	if err := h.shareLinkService.DeactivateLink(c.Request.Context(), linkID, projectID, userID); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("deactivate_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Share link deactivated"))
}

// Join handles POST /share/join/:token — public, only requires JWT
func (h *ShareLinkHandler) Join(c *gin.Context) {
	token := c.Param("token")
	if token == "" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Missing share token"))
		return
	}

	userID, ok := extractUserID(c)
	if !ok {
		return
	}
	email := extractUserEmail(c)

	result, err := h.shareLinkService.JoinViaLink(c.Request.Context(), token, userID, email)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("join_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}
