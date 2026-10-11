package handler

import (
	"errors"
	"net/http"
	"strconv"

	"lab-service/internal/dto"
	"lab-service/internal/repository"
	"lab-service/internal/runtime"
	"lab-service/internal/service"

	"github.com/gin-gonic/gin"
)

type TestCaseHandler struct {
	testCaseRepo *repository.TestCaseRepository
	labs         *repository.LabRepository
	runtimes     *runtime.Registry
}

func NewTestCaseHandler(repo *repository.TestCaseRepository, labs *repository.LabRepository, runtimes *runtime.Registry) *TestCaseHandler {
	return &TestCaseHandler{testCaseRepo: repo, labs: labs, runtimes: runtimes}
}

func (h *TestCaseHandler) CreateTestCase(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 2*1024*1024)
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.CreateTestCaseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	if err := dto.ValidateTestCases([]dto.CreateTestCaseRequest{req}); err != nil {
		c.JSON(400, dto.NewErrorResponse("validation_error", err.Error()))
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
	sampleOnly := userRole != "ADMIN"
	if userRole == "TEACHER" {
		owner, err := h.labs.GetCreatorID(c.Request.Context(), labID)
		if err != nil {
			c.JSON(404, dto.NewErrorResponse("not_found", "Lab not found"))
			return
		}
		sampleOnly = owner != c.GetInt64("user_id")
	}

	cases, err := h.testCaseRepo.ListByLab(c.Request.Context(), labID, sampleOnly)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	if cases == nil {
		cases = []dto.TestCaseResponse{}
	}
	if !sampleOnly {
		c.JSON(http.StatusOK, gin.H{"success": true, "data": cases, "revision": repository.SuiteRevision(cases)})
		return
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
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 2*1024*1024)
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.BulkCreateTestCasesRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	if err := dto.ValidateTestCases(req.TestCases); err != nil {
		c.JSON(400, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	results, err := h.testCaseRepo.BulkCreate(c.Request.Context(), labID, req.TestCases)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusCreated, dto.NewSuccessResponse("Test cases created", results))
}

func (h *TestCaseHandler) UpdateTestCase(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 2*1024*1024)
	tcID, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	var req dto.UpdateTestCaseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	if err := h.testCaseRepo.Update(c.Request.Context(), tcID, &req); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Test case updated"))
}

func (h *TestCaseHandler) ReplaceTestCases(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 2*1024*1024)
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.ReplaceTestCasesRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	if err := dto.ValidateTestCases(req.TestCases); err != nil {
		c.JSON(400, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	lab, err := h.labs.GetByID(c.Request.Context(), labID)
	if err != nil {
		c.JSON(404, dto.NewErrorResponse("not_found", "Lab not found"))
		return
	}
	if lab.Status == "PUBLISHED" {
		hasSample := false
		for _, tc := range req.TestCases {
			if tc.IsSample && !tc.IsHidden {
				hasSample = true
			}
		}
		if !hasSample {
			c.JSON(400, dto.NewErrorResponse("sample_required", "A published practice lab must retain a public sample"))
			return
		}
	}
	cases, err := h.testCaseRepo.Replace(c.Request.Context(), labID, req)
	if err != nil {
		c.JSON(409, dto.NewErrorResponse("suite_error", err.Error()))
		return
	}
	c.JSON(200, dto.NewDataResponse(cases))
}
func (h *TestCaseHandler) GenerateTestCases(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 2*1024*1024)
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	lab, err := h.labs.GetByID(c.Request.Context(), labID)
	if err != nil {
		c.JSON(404, dto.NewErrorResponse("not_found", "Lab not found"))
		return
	}
	if lab.LabType != "CODING" {
		c.JSON(409, dto.NewErrorResponse("invalid_lab", "Code generators require a coding lab"))
		return
	}
	var req service.GenerateTestCasesRequest
	if err = c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	adapter, err := h.runtimes.Get(runtime.RuntimeCoding)
	if err != nil {
		c.JSON(503, dto.NewErrorResponse("unavailable", "Coding sandbox unavailable"))
		return
	}
	cases, err := service.GenerateTestCases(c.Request.Context(), adapter, labID, c.GetInt64("user_id"), req)
	if err != nil {
		if errors.Is(err, service.ErrGeneratorUnavailable) {
			c.JSON(503, dto.NewErrorResponse("sandbox_unavailable", "Sandbox unavailable; retry when provisioned"))
			return
		}
		c.JSON(422, dto.NewErrorResponse("generator_error", err.Error()))
		return
	}
	c.JSON(200, dto.NewDataResponse(gin.H{"test_cases": cases, "apply_required": true, "seed": req.Seed}))
}
