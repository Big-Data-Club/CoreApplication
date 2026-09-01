package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"

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
		Documents json.RawMessage `json:"documents"`
		AppliedCourseID int64 `json:"applied_course_id"`
		Plan struct {
			Title, Description, Category, Level string
			Governance struct { OrganizationID int64 `json:"organization_id"`; Visibility string `json:"visibility"`; ThumbnailURL string `json:"thumbnail_url"` } `json:"governance"`
			Chapters []struct { Title, Description string; MaterialIDs []string `json:"material_ids"`; Lessons []json.RawMessage `json:"lessons"` } `json:"chapters"`
		} `json:"plan"`
	}
	if err := json.Unmarshal(bytes, &blueprint); err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", "Blueprint response không hợp lệ")); return }
	if blueprint.AppliedCourseID > 0 { c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{"course_id": blueprint.AppliedCourseID, "blueprint": result, "already_applied": true})); return }
	if blueprint.Plan.Level == "" { blueprint.Plan.Level = "ALL_LEVELS" }
	if blueprint.Plan.Governance.Visibility == "" { blueprint.Plan.Governance.Visibility = "ORG_ONLY" }
	userID, role := c.GetInt64("user_id"), getRoleFromContext(c)
	created, err := h.courses.CreateCourse(c.Request.Context(), &dto.CreateCourseRequest{Title: blueprint.Plan.Title, Description: blueprint.Plan.Description, Category: blueprint.Plan.Category, Level: blueprint.Plan.Level, ThumbnailURL: blueprint.Plan.Governance.ThumbnailURL, OrgID: blueprint.Plan.Governance.OrganizationID, Visibility: blueprint.Plan.Governance.Visibility}, userID)
	if err != nil { c.JSON(422, dto.NewErrorResponse("materialize_error", err.Error())); return }
	rollback := func(cause error) { _ = h.courses.DeleteCourse(c.Request.Context(), created.ID, userID, "SYSTEM_ROLLBACK", ""); c.JSON(500, dto.NewErrorResponse("materialize_error", fmt.Sprintf("Không thể tạo đầy đủ course: %v", cause))) }
	var documents []document
	if len(blueprint.Documents) > 0 && string(blueprint.Documents) != "null" {
		// Legacy MCP blueprints stored a display-name object instead of LMS
		// documents. Only a real array is eligible for document materialisation.
		_ = json.Unmarshal(blueprint.Documents, &documents)
	}
	files := map[string]document{}
	for _, file := range documents { files[file.ID] = file }
	for sectionIndex, chapter := range blueprint.Plan.Chapters {
		section, err := h.courses.CreateSection(c.Request.Context(), created.ID, &dto.CreateSectionRequest{Title: chapter.Title, Description: chapter.Description, OrderIndex: sectionIndex}, userID, role); if err != nil { rollback(err); return }
		contentIndex := 0
		for _, materialID := range chapter.MaterialIDs {
			file, ok := files[materialID]; if !ok { rollback(fmt.Errorf("tài liệu %s không tồn tại", materialID)); return }
			_, err = h.courses.CreateContent(c.Request.Context(), section.ID, &dto.CreateContentRequest{Type: "DOCUMENT", Title: file.Filename, OrderIndex: contentIndex, Metadata: map[string]interface{}{"file_path": file.FilePath, "file_name": file.Filename, "file_type": file.ContentType, "blueprint_id": c.Param("blueprintId")}}, userID, role)
			if err != nil { rollback(err); return }
			contentIndex++
		}
		for lessonIndex, rawLesson := range chapter.Lessons {
			var item struct { Title string `json:"title"`; Description string `json:"description"`; Markdown string `json:"markdown"`; Content string `json:"content"` }
			if err := json.Unmarshal(rawLesson, &item); err != nil {
				var plainTitle string
				if stringErr := json.Unmarshal(rawLesson, &plainTitle); stringErr != nil { rollback(fmt.Errorf("bài học %d trong chương %s không hợp lệ", lessonIndex+1, chapter.Title)); return }
				item.Title = plainTitle
			}
			markdown := item.Markdown; if markdown == "" { markdown = item.Content }; if markdown == "" { markdown = item.Description }
			_, err = h.courses.CreateContent(c.Request.Context(), section.ID, &dto.CreateContentRequest{Type: "TEXT", Title: item.Title, Description: item.Description, OrderIndex: contentIndex, Metadata: map[string]interface{}{"content": markdown, "blueprint_id": c.Param("blueprintId"), "source": "MCP_BLUEPRINT"}}, userID, role)
			if err != nil { rollback(err); return }
			contentIndex++
		}
	}
	if _, err := h.ai.MarkCourseBlueprintApplied(c.Request.Context(), c.Param("blueprintId"), userID, created.ID); err != nil { rollback(fmt.Errorf("không thể ghi nhận blueprint đã áp dụng: %w", err)); return }
	c.JSON(http.StatusCreated, dto.NewDataResponse(map[string]interface{}{"course_id": created.ID, "blueprint": result}))
}

func (h *CourseBlueprintHandler) Cancel(c *gin.Context) {
	// Cancellation is forwarded through the same authenticated boundary.
	var ignored map[string]interface{}
	if err := h.ai.CancelCourseBlueprint(c.Request.Context(), c.Param("blueprintId"), c.GetInt64("user_id"), &ignored); err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	c.JSON(http.StatusOK, dto.NewMessageResponse("Đã hủy đề xuất khóa học"))
}

func (h *CourseBlueprintHandler) CreateMaterialRouting(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64); if err != nil { c.JSON(400, dto.NewErrorResponse("invalid_id", "Course ID không hợp lệ")); return }
	userID, role := c.GetInt64("user_id"), getRoleFromContext(c)
	if role != "TEACHER" && role != "ADMIN" { c.JSON(403, dto.NewErrorResponse("forbidden", "Chỉ giảng viên có thể phân loại tài liệu")); return }
	sections, err := h.courses.ListSections(c.Request.Context(), courseID, userID, role); if err != nil { c.JSON(403, dto.NewErrorResponse("forbidden", err.Error())); return }
	if len(sections) == 0 { c.JSON(422, dto.NewErrorResponse("validation_error", "Khóa học chưa có chương")); return }
	var body struct { Documents []map[string]interface{} `json:"documents"` }
	if err := c.ShouldBindJSON(&body); err != nil || len(body.Documents) == 0 { c.JSON(400, dto.NewErrorResponse("validation_error", "Cần ít nhất một tài liệu")); return }
	sectionPayload := make([]map[string]interface{}, 0, len(sections)); for _, item := range sections { sectionPayload = append(sectionPayload, map[string]interface{}{"id": item.ID, "title": item.Title, "description": item.Description}) }
	result, err := h.ai.CreateMaterialRouting(c.Request.Context(), map[string]interface{}{"owner_id": userID, "course_id": courseID, "documents": body.Documents, "sections": sectionPayload})
	if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }; c.JSON(202, dto.NewDataResponse(result))
}

func (h *CourseBlueprintHandler) GetMaterialRouting(c *gin.Context) {
	result, err := h.ai.GetMaterialRouting(c.Request.Context(), c.Param("routingId"), c.GetInt64("user_id")); if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	c.JSON(200, dto.NewDataResponse(result))
}

func (h *CourseBlueprintHandler) ApplyMaterialRouting(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64); if err != nil { c.JSON(400, dto.NewErrorResponse("invalid_id", "Course ID không hợp lệ")); return }
	userID, role := c.GetInt64("user_id"), getRoleFromContext(c)
	var body struct { RoutingID string `json:"routing_id"`; Assignments []struct { DocumentID string `json:"document_id"`; SectionID int64 `json:"section_id"`; Title string `json:"title"`; Description string `json:"description"`; IsMandatory bool `json:"is_mandatory"` } `json:"assignments"` }
	if err := c.ShouldBindJSON(&body); err != nil { c.JSON(400, dto.NewErrorResponse("validation_error", err.Error())); return }
	jobRaw, err := h.ai.GetMaterialRouting(c.Request.Context(), body.RoutingID, userID); if err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", err.Error())); return }
	var job struct { Status string `json:"status"`; CourseID int64 `json:"course_id"`; Documents []struct { ID string `json:"id"`; Filename string `json:"filename"`; FilePath string `json:"file_path"`; ContentType string `json:"content_type"` } `json:"documents"` }; encoded, _ := json.Marshal(jobRaw); if err := json.Unmarshal(encoded, &job); err != nil { c.JSON(502, dto.NewErrorResponse("ai_error", "Routing response không hợp lệ")); return }
	if job.Status != "READY" || job.CourseID != courseID { c.JSON(409, dto.NewErrorResponse("invalid_state", "Đề xuất chưa sẵn sàng hoặc không thuộc khóa học")); return }
	sections, err := h.courses.ListSections(c.Request.Context(), courseID, userID, role); if err != nil { c.JSON(403, dto.NewErrorResponse("forbidden", err.Error())); return }
	allowed := map[int64]bool{}; nextOrder := map[int64]int{}; for _, s := range sections { allowed[s.ID] = true; items, _ := h.courses.ListContent(c.Request.Context(), s.ID, userID, role); nextOrder[s.ID] = len(items) }
	documents := map[string]struct { Filename, FilePath, ContentType string }{}; for _, item := range job.Documents { documents[item.ID] = struct { Filename, FilePath, ContentType string }{item.Filename,item.FilePath,item.ContentType} }
	created := 0
	for _, assignment := range body.Assignments { doc, ok := documents[assignment.DocumentID]; if !ok || !allowed[assignment.SectionID] { c.JSON(422, dto.NewErrorResponse("validation_error", "Tài liệu hoặc chương không hợp lệ")); return }; title := assignment.Title; if title == "" { title = doc.Filename }; _, err = h.courses.CreateContent(c.Request.Context(), assignment.SectionID, &dto.CreateContentRequest{Type:"DOCUMENT", Title:title, Description:assignment.Description, OrderIndex:nextOrder[assignment.SectionID], IsMandatory:assignment.IsMandatory, Metadata:map[string]interface{}{"file_path":doc.FilePath,"file_name":doc.Filename,"file_type":doc.ContentType,"routing_id":body.RoutingID}}, userID, role); if err != nil { c.JSON(500, dto.NewErrorResponse("materialize_error", err.Error())); return }; nextOrder[assignment.SectionID]++; created++ }
	c.JSON(201, dto.NewDataResponse(map[string]interface{}{"created":created}))
}
