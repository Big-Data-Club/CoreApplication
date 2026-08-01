package handler

import (
	"net/http"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/pkg/ai"

	"github.com/gin-gonic/gin"
)

// CourseBlueprintHandler is the authenticated BFF boundary for the AI
// curriculum workflow. It deliberately overwrites identity and organization
// allow-lists supplied by the browser before forwarding to ai-service.
type CourseBlueprintHandler struct { ai *ai.Client; orgs *repository.OrganizationRepository }

func NewCourseBlueprintHandler(client *ai.Client, orgs *repository.OrganizationRepository) *CourseBlueprintHandler {
	return &CourseBlueprintHandler{ai: client, orgs: orgs}
}

func (h *CourseBlueprintHandler) allowedOrgs(c *gin.Context) ([]int64, error) {
	rows, err := h.orgs.GetUserOrgs(c.Request.Context(), c.GetInt64("user_id")); if err != nil { return nil, err }
	ids := make([]int64, 0, len(rows)); for _, row := range rows { ids = append(ids, row.ID) }
	return ids, nil
}

func (h *CourseBlueprintHandler) Create(c *gin.Context) {
	if role := getRoleFromContext(c); role != "TEACHER" && role != "ADMIN" {
		c.JSON(403, dto.NewErrorResponse("forbidden", "Chỉ giảng viên hoặc quản trị viên có thể tạo course blueprint")); return
	}
	var body map[string]interface{}; if err := c.ShouldBindJSON(&body); err != nil { c.JSON(400, dto.NewErrorResponse("validation_error", err.Error())); return }
	orgs, err := h.allowedOrgs(c); if err != nil { c.JSON(500, dto.NewErrorResponse("internal_error", "Không thể kiểm tra organization")); return }
	if len(orgs) == 0 { c.JSON(403, dto.NewErrorResponse("forbidden", "Bạn chưa thuộc organization nào có thể tạo course")); return }
	body["owner_id"] = c.GetInt64("user_id"); body["allowed_organization_ids"] = orgs; body["origin"] = "course_create"
	result, err := h.ai.CreateCourseBlueprint(c.Request.Context(), body); if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	c.JSON(201, dto.NewDataResponse(result))
}

func (h *CourseBlueprintHandler) Update(c *gin.Context) {
	var body map[string]interface{}; if err := c.ShouldBindJSON(&body); err != nil { c.JSON(400, dto.NewErrorResponse("validation_error", err.Error())); return }
	body["owner_id"] = c.GetInt64("user_id")
	result, err := h.ai.UpdateCourseBlueprint(c.Request.Context(), c.Param("blueprintId"), body); if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

func (h *CourseBlueprintHandler) Approve(c *gin.Context) {
	// Ownership is rechecked by CourseService when the approved plan is
	// materialised. This call only transitions the review state in ai-service.
	result, err := h.ai.ApproveCourseBlueprint(c.Request.Context(), c.Param("blueprintId"), c.GetInt64("user_id")); if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}
