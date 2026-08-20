package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/service"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type LearningEventHandler struct {
	service *service.LearningEventService
}

func NewLearningEventHandler(service *service.LearningEventService) *LearningEventHandler {
	return &LearningEventHandler{service: service}
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNING EVENTS API
// ══════════════════════════════════════════════════════════════════════════════

// TrackEvent tracks a learning event
// POST /api/v1/learning-events
func (h *LearningEventHandler) TrackEvent(c *gin.Context) {
	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_id not found in context"})
		return
	}

	studentID, ok := userID.(int64)
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid user_id type"})
		return
	}

	var req service.TrackEventRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	eventID := uuid.New().String()
	event, err := h.service.TrackEvent(c.Request.Context(), studentID, eventID, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"success": true,
		"data":    event,
	})
}

// GetStudentTrajectory gets a student's learning trajectory
// GET /api/v1/students/:id/trajectory
func (h *LearningEventHandler) GetStudentTrajectory(c *gin.Context) {
	studentIDStr := c.Param("id")
	studentID, err := strconv.ParseInt(studentIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid student_id"})
		return
	}

	courseID := c.Query("course_id")
	limit := c.DefaultQuery("limit", "100")

	events, err := h.service.GetStudentEvents(c.Request.Context(), studentID, courseID, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    events,
		"count":   len(events),
	})
}

// GetStudentSkills gets a student's skill mastery states
// GET /api/v1/students/:id/skills
func (h *LearningEventHandler) GetStudentSkills(c *gin.Context) {
	studentIDStr := c.Param("id")
	studentID, err := strconv.ParseInt(studentIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid student_id"})
		return
	}

	courseID := c.Query("course_id")

	skills, err := h.service.GetStudentSkills(c.Request.Context(), studentID, courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    skills,
		"count":   len(skills),
	})
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILLS MANAGEMENT API
// ══════════════════════════════════════════════════════════════════════════════

// CreateSkill creates a new skill
// POST /api/v1/skills
func (h *LearningEventHandler) CreateSkill(c *gin.Context) {
	var req service.CreateSkillRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	skill, err := h.service.CreateSkill(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"success": true,
		"data":    skill,
	})
}

// GetSkill gets a skill by ID
// GET /api/v1/skills/:id
func (h *LearningEventHandler) GetSkill(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid skill_id"})
		return
	}

	skill, err := h.service.GetSkill(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "skill not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    skill,
	})
}

// ListSkills lists all skills
// GET /api/v1/skills
func (h *LearningEventHandler) ListSkills(c *gin.Context) {
	skills, err := h.service.ListSkills(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    skills,
		"count":   len(skills),
	})
}

// UpdateSkill updates a skill
// PUT /api/v1/skills/:id
func (h *LearningEventHandler) UpdateSkill(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid skill_id"})
		return
	}

	var req service.CreateSkillRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	skill, err := h.service.UpdateSkill(c.Request.Context(), id, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    skill,
	})
}

// DeleteSkill deletes a skill
// DELETE /api/v1/skills/:id
func (h *LearningEventHandler) DeleteSkill(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid skill_id"})
		return
	}

	if err := h.service.DeleteSkill(c.Request.Context(), id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "skill deleted successfully",
	})
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILL PREREQUISITES API
// ══════════════════════════════════════════════════════════════════════════════

// GetSkillPrerequisites gets prerequisites for a skill
// GET /api/v1/skills/:id/prerequisites
func (h *LearningEventHandler) GetSkillPrerequisites(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid skill_id"})
		return
	}

	prereqs, err := h.service.GetSkillPrerequisites(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    prereqs,
		"count":   len(prereqs),
	})
}

// AddPrerequisite adds a prerequisite to a skill
// POST /api/v1/skills/:id/prerequisites
func (h *LearningEventHandler) AddPrerequisite(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid skill_id"})
		return
	}

	var req service.AddPrerequisiteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	prereq, err := h.service.AddPrerequisite(c.Request.Context(), id, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"success": true,
		"data":    prereq,
	})
}

// DeletePrerequisite removes a prerequisite from a skill
// DELETE /api/v1/skills/:id/prerequisites/:prerequisite_id
func (h *LearningEventHandler) DeletePrerequisite(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid skill_id"})
		return
	}

	prereqIDStr := c.Param("prerequisite_id")
	prereqID, err := strconv.ParseInt(prereqIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid prerequisite_id"})
		return
	}

	if err := h.service.DeletePrerequisite(c.Request.Context(), id, prereqID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "prerequisite removed successfully",
	})
}

// ══════════════════════════════════════════════════════════════════════════════
// CONTENT SKILLS MAPPING API
// ══════════════════════════════════════════════════════════════════════════════

// MapContentToSkill maps content to a skill
// POST /api/v1/content/:id/skills
func (h *LearningEventHandler) MapContentToSkill(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid content_id"})
		return
	}

	var req service.MapSkillRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	mapping, err := h.service.MapContentToSkill(c.Request.Context(), id, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"success": true,
		"data":    mapping,
	})
}

// GetContentSkills gets skills mapped to content
// GET /api/v1/content/:id/skills
func (h *LearningEventHandler) GetContentSkills(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid content_id"})
		return
	}

	mappings, err := h.service.GetContentSkills(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    mappings,
		"count":   len(mappings),
	})
}

// DeleteContentSkill removes a skill mapping from content
// DELETE /api/v1/content/:id/skills/:skill_id
func (h *LearningEventHandler) DeleteContentSkill(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid content_id"})
		return
	}

	skillIDStr := c.Param("skill_id")
	skillID, err := strconv.ParseInt(skillIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid skill_id"})
		return
	}

	if err := h.service.DeleteContentSkill(c.Request.Context(), id, skillID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "skill mapping removed successfully",
	})
}

// MapQuestionToSkill maps a quiz question to a skill
// POST /api/v1/questions/:id/skills
func (h *LearningEventHandler) MapQuestionToSkill(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid question_id"})
		return
	}

	var req service.MapSkillRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	mapping, err := h.service.MapQuestionToSkill(c.Request.Context(), id, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"success": true,
		"data":    mapping,
	})
}

// GetQuestionSkills gets skills mapped to a question
// GET /api/v1/questions/:id/skills
func (h *LearningEventHandler) GetQuestionSkills(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid question_id"})
		return
	}

	mappings, err := h.service.GetQuestionSkills(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    mappings,
		"count":   len(mappings),
	})
}
