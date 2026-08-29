// lms-service/internal/handler/question_bank_handler.go
package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

// QuestionBankHandler - REST surface for the per-course question library.
type QuestionBankHandler struct {
	bankService *service.QuestionBankService
}

func NewQuestionBankHandler(bankService *service.QuestionBankService) *QuestionBankHandler {
	return &QuestionBankHandler{bankService: bankService}
}

func (h *QuestionBankHandler) identity(c *gin.Context) (int64, string, bool) {
	userID, ok := c.Get("user_id")
	if !ok {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User not authenticated"))
		return 0, "", false
	}
	role, _ := c.Get("user_role")
	uid, _ := userID.(int64)
	return uid, roleStr(role), true
}

func roleStr(v interface{}) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func parsePathID(c *gin.Context, name string) (int64, bool) {
	id, err := strconv.ParseInt(c.Param(name), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid "+name))
		return 0, false
	}
	return id, true
}

// CreateItems godoc
// @Summary Bulk-add questions to the course question bank
// @Tags Question Bank
// @Security BearerAuth
// @Param courseId path int true "Course ID"
// @Param request body dto.CreateBankItemsRequest true "Items (max 100)"
// @Success 200 {object} dto.SuccessResponse
// @Router /courses/{courseId}/question-bank [post]
func (h *QuestionBankHandler) CreateItems(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	courseID, ok := parsePathID(c, "courseId")
	if !ok {
		return
	}
	var req dto.CreateBankItemsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	items, err := h.bankService.CreateItems(c.Request.Context(), courseID, userID, role, &req)
	if err != nil {
		logger.Error("bank CreateItems failed", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("create_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(gin.H{"items": items, "count": len(items)}))
}

// ListItems godoc
// @Summary List / filter / paginate the question bank
// @Tags Question Bank
// @Security BearerAuth
// @Param courseId path int true "Course ID"
// @Param page query int false "Page (1-based)"
// @Param page_size query int false "Page size (max 100)"
// @Param difficulty query string false "EASY|MEDIUM|HARD"
// @Param bloom_level query string false "remember..create"
// @Param node_id query int false "Exact node"
// @Param dangling query bool false "true = items without a node"
// @Param source query string false "MANUAL|IMPORT|AI_GENERATED"
// @Param q query string false "Full-text search on question text"
// @Param sort query string false "created_at|points|difficulty"
// @Param order query string false "asc|desc"
// @Success 200 {object} dto.SuccessResponse
// @Router /courses/{courseId}/question-bank [get]
func (h *QuestionBankHandler) ListItems(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	courseID, ok := parsePathID(c, "courseId")
	if !ok {
		return
	}
	var query dto.BankListQuery
	if err := c.ShouldBindQuery(&query); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	resp, err := h.bankService.ListItems(c.Request.Context(), courseID, userID, role, query)
	if err != nil {
		logger.Error("bank ListItems failed", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("list_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(resp))
}

// Stats godoc
// @Summary Facet counts for the question bank header
// @Tags Question Bank
// @Security BearerAuth
// @Param courseId path int true "Course ID"
// @Success 200 {object} dto.SuccessResponse
// @Router /courses/{courseId}/question-bank/stats [get]
func (h *QuestionBankHandler) Stats(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	courseID, ok := parsePathID(c, "courseId")
	if !ok {
		return
	}
	stats, err := h.bankService.Stats(c.Request.Context(), courseID, userID, role)
	if err != nil {
		logger.Error("bank Stats failed", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("stats_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(stats))
}

// UpdateItem godoc
// @Summary Partially update a bank item (difficulty/node/tags/status/...)
// @Tags Question Bank
// @Security BearerAuth
// @Param itemId path int true "Bank item ID"
// @Param request body dto.UpdateBankItemRequest true "Fields to update"
// @Success 200 {object} dto.SuccessResponse
// @Router /question-bank/{itemId} [patch]
func (h *QuestionBankHandler) UpdateItem(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	itemID, ok := parsePathID(c, "itemId")
	if !ok {
		return
	}
	var req dto.UpdateBankItemRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	item, err := h.bankService.UpdateItem(c.Request.Context(), itemID, userID, role, &req)
	if err != nil {
		logger.Error("bank UpdateItem failed", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(item))
}

// DeleteItem godoc
// @Summary Delete a bank item
// @Tags Question Bank
// @Security BearerAuth
// @Param itemId path int true "Bank item ID"
// @Success 200 {object} dto.SuccessResponse
// @Router /question-bank/{itemId} [delete]
func (h *QuestionBankHandler) DeleteItem(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	itemID, ok := parsePathID(c, "itemId")
	if !ok {
		return
	}
	if err := h.bankService.DeleteItem(c.Request.Context(), itemID, userID, role); err != nil {
		logger.Error("bank DeleteItem failed", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("delete_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Question bank item deleted"))
}

// CreateQuizFromBank godoc
// @Summary Assemble a new quiz from selected bank items (items are copied, not moved)
// @Tags Question Bank
// @Security BearerAuth
// @Param courseId path int true "Course ID"
// @Param request body dto.CreateQuizFromBankRequest true "Quiz meta + item_ids"
// @Success 200 {object} dto.SuccessResponse
// @Router /courses/{courseId}/question-bank/create-quiz [post]
func (h *QuestionBankHandler) CreateQuizFromBank(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	courseID, ok := parsePathID(c, "courseId")
	if !ok {
		return
	}
	var req dto.CreateQuizFromBankRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	resp, err := h.bankService.CreateQuizFromBank(c.Request.Context(), courseID, userID, role, &req)
	if err != nil {
		logger.Error("CreateQuizFromBank failed", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("create_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(resp))
}

func (h *QuestionBankHandler) SuggestQuizMetadata(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	courseID, ok := parsePathID(c, "courseId")
	if !ok {
		return
	}
	var req dto.SuggestQuizMetadataRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	resp, err := h.bankService.SuggestQuizMetadata(c.Request.Context(), courseID, userID, role, &req)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("suggest_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(resp))
}

// GenerateToBank godoc
// @Summary AI auto-generate classified questions INTO the bank
// @Description Nodes can be selected explicitly; an empty selection samples the
// @Description course knowledge graph. The generator avoids duplicates. Generated
// @Description items are persisted with source=AI_GENERATED.
// @Tags Question Bank
// @Security BearerAuth
// @Param courseId path int true "Course ID"
// @Param request body service.GenerateIntoBankRequest true "Generation options"
// @Success 200 {object} dto.SuccessResponse
// @Router /courses/{courseId}/question-bank/generate [post]
func (h *QuestionBankHandler) GenerateToBank(c *gin.Context) {
	userID, role, ok := h.identity(c)
	if !ok {
		return
	}
	courseID, ok := parsePathID(c, "courseId")
	if !ok {
		return
	}
	var req service.GenerateIntoBankRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	items, rejected, err := h.bankService.GenerateIntoBank(c.Request.Context(), courseID, userID, role, &req)
	if err != nil {
		logger.Error("GenerateToBank failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("generation_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(gin.H{
		"items": items, "count": len(items), "rejected_count": rejected,
	}))
}
