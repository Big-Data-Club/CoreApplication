package handler

import (
	"encoding/json"
	"fmt"
	"net/http"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/internal/service"
	"example/hello/pkg/ai"

	"github.com/gin-gonic/gin"
)

// CourseBlueprintHandler is the authenticated BFF boundary for the AI
// curriculum workflow. It deliberately overwrites identity and organization
// allow-lists supplied by the browser before forwarding to ai-service.
type CourseBlueprintHandler struct { ai *ai.Client; orgs *repository.OrganizationRepository; courses *service.CourseService }

func NewCourseBlueprintHandler(client *ai.Client, orgs *repository.OrganizationRepository, courses *service.CourseService) *CourseBlueprintHandler {
	return &CourseBlueprintHandler{ai: client, orgs: orgs, courses: courses}
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
	c.JSON(http.StatusAccepted, dto.NewDataResponse(result))
}

func (h *CourseBlueprintHandler) Get(c *gin.Context) {
	result, err := h.ai.GetCourseBlueprint(c.Request.Context(), c.Param("blueprintId"), c.GetInt64("user_id"))
	if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
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

// Apply approves then materialises all LMS rows on the server. If a later
// section/content insert fails, the freshly-created draft course is removed as
// compensation so teachers never inherit a half-built course.
func (h *CourseBlueprintHandler) Apply(c *gin.Context) {
	result, err := h.ai.ApproveCourseBlueprint(c.Request.Context(), c.Param("blueprintId"), c.GetInt64("user_id"))
	if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	bytes, _ := json.Marshal(result)
	type document struct { ID string `json:"id"`; Filename string `json:"filename"`; FilePath string `json:"file_path"`; ContentType string `json:"content_type"` }
	var blueprint struct {
		Documents []document `json:"documents"`
		Plan struct {
			Title, Description, Category, Level string
			Governance struct { OrganizationID int64 `json:"organization_id"`; Visibility string `json:"visibility"`; ThumbnailURL string `json:"thumbnail_url"` } `json:"governance"`
			Chapters []struct { Title, Description string; MaterialIDs []string `json:"material_ids"` } `json:"chapters"`
		} `json:"plan"`
	}
	if err := json.Unmarshal(bytes, &blueprint); err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", "Blueprint response không hợp lệ")); return }
	userID, role := c.GetInt64("user_id"), getRoleFromContext(c)
	created, err := h.courses.CreateCourse(c.Request.Context(), &dto.CreateCourseRequest{Title: blueprint.Plan.Title, Description: blueprint.Plan.Description, Category: blueprint.Plan.Category, Level: blueprint.Plan.Level, ThumbnailURL: blueprint.Plan.Governance.ThumbnailURL, OrgID: blueprint.Plan.Governance.OrganizationID, Visibility: blueprint.Plan.Governance.Visibility}, userID)
	if err != nil { c.JSON(422, dto.NewErrorResponse("materialize_error", err.Error())); return }
	rollback := func(cause error) { _ = h.courses.DeleteCourse(c.Request.Context(), created.ID, userID, role); c.JSON(500, dto.NewErrorResponse("materialize_error", fmt.Sprintf("Không thể tạo đầy đủ course: %v", cause))) }
	files := map[string]document{}
	for _, file := range blueprint.Documents { files[file.ID] = file }
	for sectionIndex, chapter := range blueprint.Plan.Chapters {
		section, err := h.courses.CreateSection(c.Request.Context(), created.ID, &dto.CreateSectionRequest{Title: chapter.Title, Description: chapter.Description, OrderIndex: sectionIndex}, userID, role); if err != nil { rollback(err); return }
		for contentIndex, materialID := range chapter.MaterialIDs {
			file, ok := files[materialID]; if !ok { rollback(fmt.Errorf("tài liệu %s không tồn tại", materialID)); return }
			_, err = h.courses.CreateContent(c.Request.Context(), section.ID, &dto.CreateContentRequest{Type: "DOCUMENT", Title: file.Filename, OrderIndex: contentIndex, Metadata: map[string]interface{}{"file_path": file.FilePath, "file_name": file.Filename, "file_type": file.ContentType, "blueprint_id": c.Param("blueprintId")}}, userID, role)
			if err != nil { rollback(err); return }
		}
	}
	c.JSON(http.StatusCreated, dto.NewDataResponse(map[string]interface{}{"course_id": created.ID, "blueprint": result}))
}

func (h *CourseBlueprintHandler) Cancel(c *gin.Context) {
	// Cancellation is forwarded through the same authenticated boundary.
	var ignored map[string]interface{}
	if err := h.ai.CancelCourseBlueprint(c.Request.Context(), c.Param("blueprintId"), c.GetInt64("user_id"), &ignored); err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	c.JSON(http.StatusOK, dto.NewMessageResponse("Đã hủy đề xuất khóa học"))
}
