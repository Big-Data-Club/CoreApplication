package handler

import (
	"net/http"
	"strconv"

	"lab-service/internal/dto"
	"lab-service/internal/repository"

	"github.com/gin-gonic/gin"
)

type LeaderboardHandler struct {
	repo *repository.LeaderboardRepository
}

func NewLeaderboardHandler(repo *repository.LeaderboardRepository) *LeaderboardHandler {
	return &LeaderboardHandler{repo: repo}
}

func (h *LeaderboardHandler) GetLabLeaderboard(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	sortBy := c.DefaultQuery("sort", "score")
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "50"))

	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 50
	}
	offset := (page - 1) * pageSize

	entries, total, err := h.repo.GetLabLeaderboard(c.Request.Context(), labID, sortBy, pageSize, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	if entries == nil {
		entries = []repository.LeaderboardEntry{}
	}
	c.JSON(http.StatusOK, dto.NewListResponse(entries, page, pageSize, total))
}
