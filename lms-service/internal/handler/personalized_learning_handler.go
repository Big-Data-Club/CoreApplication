package handler

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type PersonalizedLearningHandler struct {
	learningEventService *service.LearningEventService
	courseService        *service.CourseService
}

func NewPersonalizedLearningHandler(
	learningEventService *service.LearningEventService,
	courseService *service.CourseService,
) *PersonalizedLearningHandler {
	return &PersonalizedLearningHandler{
		learningEventService: learningEventService,
		courseService:        courseService,
	}
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNING EVENTS API
// ══════════════════════════════════════════════════════════════════════════════

// TrackLearningEvent tracks a learning event
// @Summary Track learning event
// @Description Track student learning interactions for personalization
// @Tags personalized-learning
// @Accept json
// @Produce json
// @Param event body dto.TrackLearningEventRequest true "Learning event"
// @Security BearerAuth
// @Success 201 {object} dto.DataResponse{data=dto.LearningEventResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Failure 401 {object} dto.ErrorResponse
// @Router /learning-events [post]
func (h *PersonalizedLearningHandler) TrackLearningEvent(c *gin.Context) {
	userID := c.GetInt64("user_id")

	var req dto.TrackLearningEventRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	eventID := uuid.New().String()

	// Convert DTO to service request
	serviceReq := &service.TrackEventRequest{
		EventType:      req.EventType,
		SessionID:      req.SessionID,
		CourseID:       req.CourseID,
		LessonID:       req.LessonID,
		QuestionID:     req.QuestionID,
		SkillID:        req.SkillID,
		Difficulty:     req.Difficulty,
		Correct:        req.Correct,
		AttemptNo:      req.AttemptNo,
		ResponseTimeMs: req.ResponseTimeMs,
		HintCount:      req.HintCount,
		Metadata:       req.Metadata,
	}

	event, err := h.learningEventService.TrackEvent(c.Request.Context(), userID, eventID, serviceReq)
	if err != nil {
		logger.Error("Failed to track learning event", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to track learning event"))
		return
	}

	// Convert to response DTO
	response := h.convertToLearningEventResponse(event)

	c.JSON(http.StatusCreated, dto.NewDataResponse(response))
}

// GetStudentSkillsOverview gets comprehensive skill overview for student
// @Summary Get student skills overview
// @Description Get all skills with mastery levels, recommendations, and visual progress
// @Tags personalized-learning
// @Produce json
// @Param studentId path int true "Student ID"
// @Param course_id query int false "Filter by course ID"
// @Security BearerAuth
// @Success 200 {object} dto.DataResponse{data=dto.StudentSkillsOverviewResponse}
// @Failure 404 {object} dto.ErrorResponse
// @Router /students/{studentId}/skills-overview [get]
func (h *PersonalizedLearningHandler) GetStudentSkillsOverview(c *gin.Context) {
	studentIDStr := c.Param("studentId")
	studentID, err := strconv.ParseInt(studentIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_parameter", "Invalid student ID"))
		return
	}
	if !mayReadStudentLearningData(c, studentID) {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "You can only access your own learning data"))
		return
	}

	courseIDStr := c.Query("course_id")

	// Get skill states
	skillStates, err := h.learningEventService.GetStudentSkills(c.Request.Context(), studentID, courseIDStr)
	if err != nil {
		logger.Error("Failed to get student skills", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to get skills"))
		return
	}

	// Convert to UI-friendly response
	overview := h.buildSkillsOverview(studentID, courseIDStr, skillStates)

	c.JSON(http.StatusOK, dto.NewDataResponse(overview))
}

// GetDailyRecommendations gets personalized daily learning recommendations
// @Summary Get daily recommendations
// @Description Get today's personalized learning plan with priority content
// @Tags personalized-learning
// @Produce json
// @Param studentId path int true "Student ID"
// @Param time_budget query int false "Available time in minutes (default: 30)"
// @Security BearerAuth
// @Success 200 {object} dto.DataResponse{data=dto.DailyRecommendationsResponse}
// @Router /students/{studentId}/daily-recommendations [get]
func (h *PersonalizedLearningHandler) GetDailyRecommendations(c *gin.Context) {
	studentIDStr := c.Param("studentId")
	studentID, err := strconv.ParseInt(studentIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_parameter", "Invalid student ID"))
		return
	}
	if !mayReadStudentLearningData(c, studentID) {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "You can only access your own learning data"))
		return
	}

	timeBudget := 30 // default 30 minutes
	if timeBudgetStr := c.Query("time_budget"); timeBudgetStr != "" {
		if parsed, err := strconv.Atoi(timeBudgetStr); err == nil && parsed >= 5 && parsed <= 120 {
			timeBudget = parsed
		} else {
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_parameter", "time_budget must be between 5 and 120"))
			return
		}
	}

	// Get skill states to determine recommendations
	skillStates, err := h.learningEventService.GetStudentSkills(c.Request.Context(), studentID, "")
	if err != nil {
		logger.Error("Failed to get student skills for recommendations", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to get recommendations"))
		return
	}

	// Build daily recommendations
	recommendations, err := h.buildDailyRecommendations(c.Request.Context(), studentID, skillStates, timeBudget)
	if err != nil {
		logger.Error("Failed to build daily recommendations", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to build recommendations"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(recommendations))
}

// GetDiscoverCoursesRecommendations gets personalized course recommendations
// @Summary Get course discovery recommendations
// @Description Get personalized course recommendations based on skills and interests
// @Tags personalized-learning
// @Produce json
// @Param studentId path int true "Student ID"
// @Param limit query int false "Number of recommendations (default: 10)"
// @Security BearerAuth
// @Success 200 {object} dto.DataResponse{data=dto.DiscoverCoursesRecommendationResponse}
// @Router /students/{studentId}/discover-courses [get]
func (h *PersonalizedLearningHandler) GetDiscoverCoursesRecommendations(c *gin.Context) {
	studentIDStr := c.Param("studentId")
	studentID, err := strconv.ParseInt(studentIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_parameter", "Invalid student ID"))
		return
	}
	if !mayReadStudentLearningData(c, studentID) {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "You can only access your own learning data"))
		return
	}

	limit := 10
	if limitStr := c.Query("limit"); limitStr != "" {
		if parsed, err := strconv.Atoi(limitStr); err == nil && parsed > 0 && parsed <= 50 {
			limit = parsed
		} else {
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_parameter", "limit must be between 1 and 50"))
			return
		}
	}

	// Get student's skill profile
	skillStates, err := h.learningEventService.GetStudentSkills(c.Request.Context(), studentID, "")
	if err != nil {
		logger.Error("Failed to get student skills", err)
		skillStates = []models.LearnerSkillStateWithSkill{} // Continue with empty profile
	}

	// Get available courses (call course service)
	// TODO: This should call a method that filters by skills
	// For now, we'll get published courses and rank them
	courses, err := h.buildCourseRecommendations(c.Request.Context(), studentID, skillStates, limit)
	if err != nil {
		logger.Error("Failed to get course recommendations", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to get course recommendations"))
		return
	}

	response := dto.DiscoverCoursesRecommendationResponse{
		Courses:              courses,
		RecommendationReason: h.getPersonalizationMessage(len(skillStates)),
		PersonalizationLevel: h.getPersonalizationLevel(len(skillStates)),
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(response))
}

// GetLearningTrajectory gets student's complete learning history
// @Summary Get learning trajectory
// @Description Get student's complete learning history with timeline view
// @Tags personalized-learning
// @Produce json
// @Param studentId path int true "Student ID"
// @Param course_id query int false "Filter by course ID"
// @Param limit query int false "Number of events (default: 100)"
// @Security BearerAuth
// @Success 200 {object} dto.DataResponse{data=dto.StudentLearningTrajectoryResponse}
// @Router /students/{studentId}/trajectory [get]
func (h *PersonalizedLearningHandler) GetLearningTrajectory(c *gin.Context) {
	studentIDStr := c.Param("studentId")
	studentID, err := strconv.ParseInt(studentIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_parameter", "Invalid student ID"))
		return
	}
	if !mayReadStudentLearningData(c, studentID) {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "You can only access your own learning data"))
		return
	}

	courseID := c.Query("course_id")
	limit := c.DefaultQuery("limit", "100")
	parsedLimit, err := strconv.Atoi(limit)
	if err != nil || parsedLimit < 1 || parsedLimit > 500 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_parameter", "limit must be between 1 and 500"))
		return
	}

	events, err := h.learningEventService.GetStudentEvents(c.Request.Context(), studentID, courseID, limit)
	if err != nil {
		logger.Error("Failed to get learning trajectory", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to get trajectory"))
		return
	}

	// Convert to trajectory response with timeline
	trajectory := h.buildTrajectoryResponse(studentID, events)

	c.JSON(http.StatusOK, dto.NewDataResponse(trajectory))
}

// ══════════════════════════════════════════════════════════════════════════════
// HELPER METHODS
// ══════════════════════════════════════════════════════════════════════════════

func (h *PersonalizedLearningHandler) convertToLearningEventResponse(event *models.LearningEvent) dto.LearningEventResponse {
	response := dto.LearningEventResponse{
		ID:        event.ID,
		EventID:   event.EventID,
		EventType: event.EventType,
		StudentID: event.StudentID,
		CreatedAt: event.CreatedAt,
	}

	if event.SessionID.Valid {
		response.SessionID = event.SessionID.String
	}
	if event.CourseID.Valid {
		courseID := event.CourseID.Int64
		response.CourseID = &courseID
	}
	if event.LessonID.Valid {
		lessonID := event.LessonID.Int64
		response.LessonID = &lessonID
	}
	if event.QuestionID.Valid {
		questionID := event.QuestionID.Int64
		response.QuestionID = &questionID
	}
	if event.SkillID.Valid {
		skillID := event.SkillID.Int64
		response.SkillID = &skillID
	}
	if event.Difficulty.Valid {
		difficulty := event.Difficulty.Float64
		response.Difficulty = &difficulty
	}
	if event.Correct.Valid {
		correct := event.Correct.Bool
		response.Correct = &correct
	}
	if event.AttemptNo.Valid {
		attemptNo := int(event.AttemptNo.Int32)
		response.AttemptNo = &attemptNo
	}
	if event.ResponseTimeMs.Valid {
		responseTime := event.ResponseTimeMs.Int64
		response.ResponseTimeMs = &responseTime
	}
	if event.HintCount.Valid {
		hintCount := int(event.HintCount.Int32)
		response.HintCount = &hintCount
	}

	return response
}

func (h *PersonalizedLearningHandler) buildSkillsOverview(
	studentID int64,
	courseID string,
	skillStates []models.LearnerSkillStateWithSkill,
) dto.StudentSkillsOverviewResponse {

	var courseIDPtr *int64
	if courseID != "" {
		if parsed, err := strconv.ParseInt(courseID, 10, 64); err == nil {
			courseIDPtr = &parsed
		}
	}

	overview := dto.StudentSkillsOverviewResponse{
		StudentID:          studentID,
		CourseID:           courseIDPtr,
		TotalSkills:        len(skillStates),
		Skills:             make([]dto.LearnerSkillStateResponse, 0, len(skillStates)),
		RecommendedActions: []dto.RecommendedAction{},
	}

	masteredCount := 0
	strugglingCount := 0
	totalMastery := 0.0

	for _, state := range skillStates {
		masteryLevel := h.getMasteryLevel(state.MasteryScore)

		if masteryLevel == "mastered" {
			masteredCount++
		} else if masteryLevel == "struggling" {
			strugglingCount++
		}

		totalMastery += state.MasteryScore

		skillResponse := dto.LearnerSkillStateResponse{
			SkillID:           state.SkillID,
			SkillName:         state.SkillName,
			SkillDescription:  state.SkillDescription.String,
			MasteryScore:      state.MasteryScore,
			MasteryLevel:      masteryLevel,
			MasteryPercentage: int(state.MasteryScore * 100),
			ConfidenceScore:   state.ConfidenceScore,
			AttemptCount:      state.AttemptCount,
			Accuracy:          state.Accuracy,
			HintDependency:    state.HintDependency,
			UpdatedAt:         state.UpdatedAt,
			IsStruggling:      masteryLevel == "struggling",
			ProgressIndicator: h.getProgressIndicator(state.MasteryScore),
			NextAction:        h.getNextAction(state.MasteryScore),
		}

		if state.AvgResponseTimeMs.Valid {
			avgTime := state.AvgResponseTimeMs.Int64
			skillResponse.AvgResponseTimeMs = &avgTime
		}
		if state.RecommendedDifficulty.Valid {
			recDiff := state.RecommendedDifficulty.Float64
			skillResponse.RecommendedDifficulty = &recDiff
		}
		if state.LastPracticedAt.Valid {
			skillResponse.LastPracticedAt = &state.LastPracticedAt.Time
			skillResponse.NeedsReview = h.needsReview(state.LastPracticedAt.Time, state.MasteryScore)
		}

		overview.Skills = append(overview.Skills, skillResponse)
	}

	overview.MasteredSkills = masteredCount
	overview.StrugglingSkills = strugglingCount

	if len(skillStates) > 0 {
		overview.OverallProgress = int((totalMastery / float64(len(skillStates))) * 100)
	}

	// Generate top 3 recommended actions
	overview.RecommendedActions = h.generateRecommendedActions(skillStates)

	return overview
}

func (h *PersonalizedLearningHandler) getMasteryLevel(score float64) string {
	if score < 0.3 {
		return "struggling"
	} else if score < 0.6 {
		return "developing"
	} else if score < 0.8 {
		return "advancing"
	}
	return "mastered"
}

func (h *PersonalizedLearningHandler) getProgressIndicator(score float64) string {
	if score < 0.3 {
		return "🔴" // Red - struggling
	} else if score < 0.6 {
		return "🟡" // Yellow - developing
	} else if score < 0.8 {
		return "🟢" // Green - advancing
	}
	return "⭐" // Star - mastered
}

func (h *PersonalizedLearningHandler) getNextAction(score float64) string {
	if score < 0.3 {
		return "review"
	} else if score < 0.6 {
		return "practice"
	} else if score < 0.8 {
		return "advance"
	}
	return "maintain"
}

func (h *PersonalizedLearningHandler) needsReview(lastPracticed time.Time, mastery float64) bool {
	if mastery < 0.8 {
		return false // Not yet mastered
	}
	daysSince := time.Since(lastPracticed).Hours() / 24
	return daysSince >= 7 // Needs review if not practiced for 7 days
}

func (h *PersonalizedLearningHandler) generateRecommendedActions(states []models.LearnerSkillStateWithSkill) []dto.RecommendedAction {
	actions := []dto.RecommendedAction{}

	// Priority 1: Struggling skills
	for _, state := range states {
		if state.MasteryScore < 0.3 && state.AttemptCount > 0 {
			actions = append(actions, dto.RecommendedAction{
				Action:     "review",
				SkillID:    state.SkillID,
				SkillName:  state.SkillName,
				Reason:     fmt.Sprintf("Bạn đang gặp khó khăn với %s (%.0f%% thành thạo)", state.SkillName, state.MasteryScore*100),
				Priority:   1,
				Icon:       "🔴",
				ActionText: "Ôn tập ngay",
			})
			if len(actions) >= 3 {
				return actions
			}
		}
	}

	// Priority 2: Developing skills (ready for practice)
	for _, state := range states {
		if state.MasteryScore >= 0.3 && state.MasteryScore < 0.6 {
			actions = append(actions, dto.RecommendedAction{
				Action:     "practice",
				SkillID:    state.SkillID,
				SkillName:  state.SkillName,
				Reason:     fmt.Sprintf("Luyện tập thêm để nâng cao %s", state.SkillName),
				Priority:   2,
				Icon:       "🟡",
				ActionText: "Luyện tập",
			})
			if len(actions) >= 3 {
				return actions
			}
		}
	}

	// Priority 3: Ready for challenge
	for _, state := range states {
		if state.MasteryScore >= 0.6 && state.MasteryScore < 0.8 {
			actions = append(actions, dto.RecommendedAction{
				Action:     "advance",
				SkillID:    state.SkillID,
				SkillName:  state.SkillName,
				Reason:     fmt.Sprintf("Sẵn sàng cho thử thách cao hơn với %s", state.SkillName),
				Priority:   3,
				Icon:       "🟢",
				ActionText: "Thử thách mới",
			})
			if len(actions) >= 3 {
				return actions
			}
		}
	}

	return actions
}

func (h *PersonalizedLearningHandler) buildDailyRecommendations(
	ctx context.Context,
	studentID int64,
	skillStates []models.LearnerSkillStateWithSkill,
	timeBudget int,
) (dto.DailyRecommendationsResponse, error) {

	hour := time.Now().Hour()
	greeting := "Chào buổi sáng!"
	if hour >= 12 && hour < 18 {
		greeting = "Chào buổi chiều!"
	} else if hour >= 18 {
		greeting = "Chào buổi tối!"
	}

	motivationalMessage := h.getMotivationalMessage(skillStates)

	recommendations := dto.DailyRecommendationsResponse{
		StudentID:               studentID,
		GeneratedAt:             time.Now(),
		Greeting:                greeting,
		MotivationalMessage:     motivationalMessage,
		PriorityRecommendations: []dto.PersonalizedRecommendationResponse{},
		OptionalRecommendations: []dto.PersonalizedRecommendationResponse{},
		SkillsNeedingReview:     []dto.LearnerSkillStateResponse{},
		LearningStreak:          0, // TODO: Calculate from events
		TodayGoal:               fmt.Sprintf("Hoàn thành %d phút học tập", timeBudget),
	}

	remainingMinutes := timeBudget
	for _, state := range skillStates {
		if len(recommendations.PriorityRecommendations) >= 3 {
			break
		}
		if remainingMinutes <= 0 {
			break
		}
		if state.AttemptCount == 0 {
			continue
		}
		targetDifficulty := 0.5
		if state.RecommendedDifficulty.Valid {
			targetDifficulty = state.RecommendedDifficulty.Float64
		}
		content, err := h.learningEventService.FindPublishedContentForSkill(ctx, state.SkillID, targetDifficulty)
		if err != nil {
			return dto.DailyRecommendationsResponse{}, err
		}
		if content == nil {
			continue
		}
		reasonType, badge, action := recommendationAction(state.MasteryScore)
		estimatedMinutes := minInt(20, remainingMinutes)
		recommendations.PriorityRecommendations = append(recommendations.PriorityRecommendations, dto.PersonalizedRecommendationResponse{
			ContentID: content.ContentID, ContentTitle: content.ContentTitle, ContentType: content.ContentType,
			SkillID: state.SkillID, SkillName: state.SkillName, Difficulty: content.Difficulty,
			CurrentMastery: state.MasteryScore, TargetMastery: minFloat(1, state.MasteryScore+0.1),
			Reason: fmt.Sprintf("%s: %s", action, state.SkillName), ReasonType: reasonType,
			EstimatedMinutes: estimatedMinutes, Priority: len(recommendations.PriorityRecommendations) + 1,
			Badge: badge, Icon: "🎯", ActionButton: action,
			ImpactDescription: "Củng cố kỹ năng dựa trên kết quả học gần đây",
		})
		remainingMinutes -= estimatedMinutes
	}
	return recommendations, nil
}

func recommendationAction(mastery float64) (reasonType, badge, action string) {
	switch {
	case mastery < 0.3:
		return "struggling", "Cần ôn tập", "Ôn tập ngay"
	case mastery < 0.6:
		return "practice", "Luyện tập", "Luyện tập"
	default:
		return "advance", "Thử thách", "Tiếp tục học"
	}
}

func minFloat(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}
func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func (h *PersonalizedLearningHandler) getMotivationalMessage(states []models.LearnerSkillStateWithSkill) string {
	if len(states) == 0 {
		return "Hãy bắt đầu hành trình học tập của bạn! 🚀"
	}

	masteredCount := 0
	for _, state := range states {
		if state.MasteryScore >= 0.8 {
			masteredCount++
		}
	}

	if masteredCount == 0 {
		return "Mỗi ngày học một chút, tiến bộ từng bước! 💪"
	} else if masteredCount < len(states)/2 {
		return fmt.Sprintf("Tuyệt vời! Bạn đã thành thạo %d kỹ năng. Tiếp tục phát huy! 🌟", masteredCount)
	} else {
		return fmt.Sprintf("Xuất sắc! %d/%d kỹ năng đã thành thạo. Bạn đang làm rất tốt! 🏆", masteredCount, len(states))
	}
}

func (h *PersonalizedLearningHandler) buildCourseRecommendations(
	ctx context.Context,
	studentID int64,
	skillStates []models.LearnerSkillStateWithSkill,
	limit int,
) ([]dto.RecommendedCourseItem, error) {
	// The catalogue is the source of truth for visible courses. Until authors
	// map course content to skills, return a clearly-labelled, real catalogue
	// fallback instead of fabricating recommendations.
	courses, _, err := h.courseService.ListPublishedCourses(ctx, studentID, dto.FilterRequest{}, limit, 0)
	if err != nil {
		return nil, err
	}
	items := make([]dto.RecommendedCourseItem, 0, len(courses))
	for _, course := range courses {
		level := course.Level
		if level == "" {
			level = "ALL_LEVELS"
		}
		items = append(items, dto.RecommendedCourseItem{
			CourseID: course.ID, Title: course.Title, Description: course.Description,
			Category: course.Category, Level: level, ThumbnailURL: course.ThumbnailURL,
			EnrollmentCount: course.EnrollmentCount, MatchScore: 0.5,
			MatchReason:        "Khóa học đang được công khai trong danh mục của bạn",
			SkillsYouWillLearn: []string{}, RelevantSkills: []string{},
			EstimatedDuration: "Tự học", DifficultyMatch: "good",
		})
	}
	return items, nil
}

func mayReadStudentLearningData(c *gin.Context, studentID int64) bool {
	if c.GetInt64("user_id") == studentID {
		return true
	}
	roles, ok := c.Get("user_roles")
	if !ok {
		return false
	}
	for _, role := range roles.([]string) {
		if role == "ADMIN" {
			return true
		}
	}
	return false
}

func (h *PersonalizedLearningHandler) getPersonalizationMessage(skillCount int) string {
	if skillCount == 0 {
		return "Các khóa học phổ biến dành cho người mới bắt đầu"
	} else if skillCount < 5 {
		return "Khóa học được gợi ý dựa trên kỹ năng bạn đã học"
	} else {
		return "Khóa học được cá nhân hóa cao dựa trên hồ sơ học tập của bạn"
	}
}

func (h *PersonalizedLearningHandler) getPersonalizationLevel(skillCount int) string {
	if skillCount == 0 {
		return "low"
	} else if skillCount < 5 {
		return "medium"
	}
	return "high"
}

func (h *PersonalizedLearningHandler) buildTrajectoryResponse(
	studentID int64,
	events []models.LearningEvent,
) dto.StudentLearningTrajectoryResponse {

	eventResponses := make([]dto.LearningEventResponse, 0, len(events))
	for _, event := range events {
		eventResponses = append(eventResponses, h.convertToLearningEventResponse(&event))
	}

	// Group events by date for timeline view
	timelineMap := make(map[string]*dto.TimelineEvent)

	for _, event := range events {
		dateStr := event.CreatedAt.Format("2006-01-02")

		if _, exists := timelineMap[dateStr]; !exists {
			timelineMap[dateStr] = &dto.TimelineEvent{
				Date:         dateStr,
				EventCount:   0,
				Events:       []dto.LearningEventResponse{},
				Achievements: []string{},
			}
		}

		timeline := timelineMap[dateStr]
		timeline.EventCount++
		timeline.Events = append(timeline.Events, h.convertToLearningEventResponse(&event))
	}

	// Convert map to slice and generate summaries
	timeline := make([]dto.TimelineEvent, 0, len(timelineMap))
	for _, t := range timelineMap {
		t.Summary = h.generateDaySummary(t.Events)
		timeline = append(timeline, *t)
	}

	dateRange := "No activity"
	if len(events) > 0 {
		oldest := events[len(events)-1].CreatedAt.Format("02/01/2006")
		newest := events[0].CreatedAt.Format("02/01/2006")
		dateRange = fmt.Sprintf("%s - %s", oldest, newest)
	}

	return dto.StudentLearningTrajectoryResponse{
		StudentID:    studentID,
		TotalEvents:  len(events),
		DateRange:    dateRange,
		Events:       eventResponses,
		TimelineView: timeline,
	}
}

func (h *PersonalizedLearningHandler) generateDaySummary(events []dto.LearningEventResponse) string {
	lessonCompleted := 0
	questionsAnswered := 0

	for _, event := range events {
		if event.EventType == "lesson_completed" {
			lessonCompleted++
		} else if event.EventType == "answer_submitted" {
			questionsAnswered++
		}
	}

	if lessonCompleted > 0 && questionsAnswered > 0 {
		return fmt.Sprintf("Hoàn thành %d bài học, trả lời %d câu hỏi", lessonCompleted, questionsAnswered)
	} else if lessonCompleted > 0 {
		return fmt.Sprintf("Hoàn thành %d bài học", lessonCompleted)
	} else if questionsAnswered > 0 {
		return fmt.Sprintf("Trả lời %d câu hỏi", questionsAnswered)
	}

	return fmt.Sprintf("%d hoạt động học tập", len(events))
}
