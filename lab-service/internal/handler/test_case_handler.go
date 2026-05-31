package handler

import (
	"net/http"
	"strconv"

	"lab-service/internal/dto"
	"lab-service/internal/repository"

	"github.com/gin-gonic/gin"
)

type TestCaseHandler struct {
	testCaseRepo *repository.TestCaseRepository
}

func NewTestCaseHandler(repo *repository.TestCaseRepository) *TestCaseHandler {
	return &TestCaseHandler{testCaseRepo: repo}
}

func (h *TestCaseHandler) CreateTestCase(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.CreateTestCaseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	tc, err := h.testCaseRepo.Create(c.Request.Context(), labID, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusCreated, dto.NewSuccessResponse("Test case created", tc))
}

func (h *TestCaseHandler) ListTestCases(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	// Teacher sees all, student sees sample only
	userRole := c.GetString("user_role")
	sampleOnly := userRole != "ADMIN" && userRole != "TEACHER"

	cases, err := h.testCaseRepo.ListByLab(c.Request.Context(), labID, sampleOnly)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	if cases == nil {
		cases = []dto.TestCaseResponse{}
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(cases))
}

func (h *TestCaseHandler) DeleteTestCase(c *gin.Context) {
	tcID, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	if err := h.testCaseRepo.Delete(c.Request.Context(), tcID); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Test case deleted"))
}

func (h *TestCaseHandler) BulkCreateTestCases(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.BulkCreateTestCasesRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	results, err := h.testCaseRepo.BulkCreate(c.Request.Context(), labID, req.TestCases)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusCreated, dto.NewSuccessResponse("Test cases created", results))
}
