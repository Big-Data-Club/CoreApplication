package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/pkg/ai"
	"example/hello/pkg/cache"
	"example/hello/pkg/logger"

	"golang.org/x/sync/errgroup"
)

type AnalyticsService struct {
	analyticsRepo  *repository.AnalyticsRepository
	courseRepo     *repository.CourseRepository
	enrollmentRepo *repository.EnrollmentRepository
	aiClient       *ai.Client
	redisCache     *cache.RedisCache
}

func NewAnalyticsService(
	analyticsRepo *repository.AnalyticsRepository,
	courseRepo *repository.CourseRepository,
	enrollmentRepo *repository.EnrollmentRepository,
	aiClient *ai.Client,
	redisCache *cache.RedisCache,
) *AnalyticsService {
	return &AnalyticsService{
		analyticsRepo:  analyticsRepo,
		courseRepo:     courseRepo,
		enrollmentRepo: enrollmentRepo,
		aiClient:       aiClient,
		redisCache:     redisCache,
	}
}

// ─── Teacher methods ──────────────────────────────────────────────────────────

func (s *AnalyticsService) GetCourseQuizAnalytics(ctx context.Context, courseID int64) ([]dto.QuizPerformanceSummary, error) {
	rows, err := s.analyticsRepo.GetCourseQuizAnalytics(ctx, courseID)
	if err != nil {
		return nil, fmt.Errorf("GetCourseQuizAnalytics: %w", err)
	}

	result := make([]dto.QuizPerformanceSummary, 0, len(rows))
	for _, r := range rows {
		item := dto.QuizPerformanceSummary{
			QuizID:         r.QuizID,
			QuizTitle:      r.QuizTitle,
			ContentID:      r.ContentID,
			TotalAttempts:  r.TotalAttempts,
			UniqueStudents: r.UniqueStudents,
			AvgScore:       nfv(r.AvgScore),
			AvgPercentage:  nfv(r.AvgPercentage),
			PassRate:       nfv(r.PassRate),
		}
		if r.PassingScore.Valid {
			v := r.PassingScore.Float64
			item.PassingScore = &v
		}
		result = append(result, item)
	}
	return result, nil
}

func (s *AnalyticsService) GetQuizAllAttempts(ctx context.Context, quizID int64) ([]dto.StudentAttemptOverview, error) {
	rows, err := s.analyticsRepo.GetQuizAllAttempts(ctx, quizID)
	if err != nil {
		return nil, fmt.Errorf("GetQuizAllAttempts: %w", err)
	}

	result := make([]dto.StudentAttemptOverview, 0, len(rows))
	for _, r := range rows {
		item := dto.StudentAttemptOverview{
			StudentID:     r.StudentID,
			StudentName:   r.StudentName,
			StudentEmail:  r.StudentEmail,
			QuizID:        r.QuizID,
			QuizTitle:     r.QuizTitle,
			AttemptNumber: r.AttemptNumber,
			TotalPoints:   r.TotalPoints,
			Status:        r.Status,
		}
		if r.EarnedPoints.Valid {
			v := r.EarnedPoints.Float64
			item.EarnedPoints = &v
		}
		if r.Percentage.Valid {
			v := r.Percentage.Float64
			item.Percentage = &v
		}
		if r.IsPassed.Valid {
			v := r.IsPassed.Bool
			item.IsPassed = &v
		}
		if r.SubmittedAt.Valid {
			v := r.SubmittedAt.Time
			item.SubmittedAt = &v
		}
		result = append(result, item)
	}
	return result, nil
}

func (s *AnalyticsService) GetQuizWrongAnswerStats(ctx context.Context, quizID int64) ([]dto.WrongAnswerStat, error) {
	rows, err := s.analyticsRepo.GetQuizWrongAnswerStats(ctx, quizID)
	if err != nil {
		return nil, fmt.Errorf("GetQuizWrongAnswerStats: %w", err)
	}

	result := make([]dto.WrongAnswerStat, 0, len(rows))
	for _, r := range rows {
		result = append(result, dto.WrongAnswerStat{
			QuestionID:   r.QuestionID,
			QuestionText: r.QuestionText,
			QuestionType: r.QuestionType,
			TotalAnswers: r.TotalAnswers,
			WrongCount:   r.WrongCount,
			WrongRate:    r.WrongRate,
		})
	}
	return result, nil
}

func (s *AnalyticsService) GetCourseStudentProgressOverview(ctx context.Context, courseID int64) ([]dto.CourseStudentProgress, error) {
	rows, err := s.analyticsRepo.GetCourseStudentProgressOverview(ctx, courseID)
	if err != nil {
		return nil, fmt.Errorf("GetCourseStudentProgressOverview: %w", err)
	}

	result := make([]dto.CourseStudentProgress, 0, len(rows))
	for _, r := range rows {
		item := dto.CourseStudentProgress{
			StudentID:        r.StudentID,
			StudentName:      r.StudentName,
			StudentEmail:     r.StudentEmail,
			TotalMandatory:   r.TotalMandatory,
			CompletedContent: r.CompletedContent,
			ProgressPercent:  r.ProgressPercent,
		}
		if r.QuizAvgScore.Valid {
			v := r.QuizAvgScore.Float64
			item.QuizAvgScore = &v
		}
		if r.LastActivity.Valid {
			v := r.LastActivity.Time
			item.LastActivity = &v
		}
		result = append(result, item)
	}
	return result, nil
}

// ─── Student method ───────────────────────────────────────────────────────────

func (s *AnalyticsService) GetMyQuizScores(ctx context.Context, courseID, studentID int64) ([]dto.StudentQuizScore, error) {
	rows, err := s.analyticsRepo.GetStudentQuizScores(ctx, courseID, studentID)
	if err != nil {
		return nil, fmt.Errorf("GetMyQuizScores: %w", err)
	}

	result := make([]dto.StudentQuizScore, 0, len(rows))
	for _, r := range rows {
		item := dto.StudentQuizScore{
			QuizID:        r.QuizID,
			QuizTitle:     r.QuizTitle,
			TotalPoints:   r.TotalPoints,
			AttemptsCount: r.AttemptsCount,
			Status:        r.Status,
		}
		if r.BestPct.Valid {
			v := r.BestPct.Float64
			item.BestPercentage = &v
		}
		if r.BestPoints.Valid {
			v := r.BestPoints.Float64
			item.BestPoints = &v
		}
		if r.IsPassed.Valid {
			v := r.IsPassed.Bool
			item.IsPassed = &v
		}
		if r.PassingScore.Valid {
			v := r.PassingScore.Float64
			item.PassingScore = &v
		}
		if r.LastAttemptAt.Valid {
			v := r.LastAttemptAt.Time
			item.LastAttemptAt = &v
		}
		result = append(result, item)
	}
	return result, nil
}

// ─── Permission helpers ───────────────────────────────────────────────────────

// VerifyCourseOwnership checks the caller owns the course, is a co-teacher, or is an admin.
func (s *AnalyticsService) VerifyCourseOwnership(ctx context.Context, courseID, userID int64, userRole string) error {
	if userRole == "ADMIN" {
		return nil
	}
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return fmt.Errorf("course not found")
	}
	if course.CreatedBy != userID {
		isCoTeacher, err := s.courseRepo.IsCoTeacher(ctx, courseID, userID)
		if err != nil || !isCoTeacher {
			return fmt.Errorf("permission denied: you don't own this course")
		}
	}
	return nil
}

// VerifyQuizCourseOwnership checks the caller owns the course that contains the quiz.
func (s *AnalyticsService) VerifyQuizCourseOwnership(ctx context.Context, quizID, userID int64, userRole string) error {
	if userRole == "ADMIN" {
		return nil
	}
	courseID, err := s.analyticsRepo.GetQuizCourseID(ctx, quizID)
	if err != nil || courseID == 0 {
		return fmt.Errorf("quiz not found")
	}
	return s.VerifyCourseOwnership(ctx, courseID, userID, userRole)
}

func (s *AnalyticsService) GetCourseStudentWeaknesses(ctx context.Context, courseID, studentID int64) (*dto.StudentWeaknessOverview, error) {
	// Call AI service which owns student_knowledge_progress
	aiNodes, err := s.aiClient.GetStudentWeaknesses(ctx, studentID, courseID)
	if err != nil {
		return nil, fmt.Errorf("GetStudentWeaknesses from AI: %w", err)
	}

	var dnodes []dto.WeakNode
	var totalWrong, totalAttempt int
	for _, n := range aiNodes {
		dnodes = append(dnodes, dto.WeakNode{
			NodeID:       n.NodeID,
			NodeTitle:    n.NameVI, // use localized name
			WrongCount:   n.WrongCount,
			TotalAttempt: n.TotalAttempt,
			MasteryLevel:   n.MasteryLevel,
			StatusLevel:    n.StatusLevel,
			FlashcardCount: n.FlashcardCount,
		})
		totalWrong += n.WrongCount
		totalAttempt += n.TotalAttempt
	}

	totalWrongPercent := 0.0
	if totalAttempt > 0 {
		totalWrongPercent = float64(totalWrong) / float64(totalAttempt) * 100
	}

	return &dto.StudentWeaknessOverview{
		TotalWrongPercent: totalWrongPercent,
		WeakNodes:         dnodes,
	}, nil
}

func (s *AnalyticsService) GetFlashcardStats(ctx context.Context, courseID, studentID int64) (*dto.FlashcardStatsResponse, error) {
	// Let's use getReviewStats for spaced_repetitions proxy
	aiStats, err := s.aiClient.GetReviewStats(ctx, studentID, courseID)
	if err != nil {
		return nil, fmt.Errorf("GetFlashcardStats from AI: %w", err)
	}
	
	resp := &dto.FlashcardStatsResponse{
		TodayDueCount: ai.GetIntField(aiStats, "due_today"),
		UpcomingCount: ai.GetIntField(aiStats, "upcoming"),
		LearningCount: ai.GetIntField(aiStats, "total_tracked"),
	}
	
	return resp, nil
}

func (s *AnalyticsService) GetStudentAnalyticsSummary(ctx context.Context, courseID, studentID int64) (*dto.StudentAnalyticsSummaryResponse, error) {
	cacheKey := fmt.Sprintf("analytics:student:%d:course:%d", studentID, courseID)

	// Check cache
	if s.redisCache != nil {
		if cachedVal, err := s.redisCache.Get(ctx, cacheKey); err == nil && cachedVal != "" {
			var cachedResp dto.StudentAnalyticsSummaryResponse
			if err := json.Unmarshal([]byte(cachedVal), &cachedResp); err == nil {
				logger.Info(fmt.Sprintf("Cache HIT: student analytics summary for student %d, course %d", studentID, courseID))
				return &cachedResp, nil
			}
		}
	}
	logger.Info(fmt.Sprintf("Cache MISS: student analytics summary for student %d, course %d", studentID, courseID))

	// Fetch data in parallel
	var (
		aiSummary      *ai.AIStudentSummary
		quizScores     []dto.StudentQuizScore
		lessonProgress dto.LessonProgressSummary
		interactions   dto.MicroInteractionSummary
		heatmap        []map[string]interface{}
	)

	g, gCtx := errgroup.WithContext(ctx)

	// Task 1: Fetch AI summary (flashcards and spaced rep quiz stats)
	g.Go(func() error {
		summary, err := s.aiClient.GetStudentAnalyticsSummary(gCtx, studentID, courseID)
		if err != nil {
			// Don't fail the entire analytics endpoint if AI service is temporarily down,
			// just log and return empty values.
			logger.Error(fmt.Sprintf("Failed to fetch student summary from AI service: %v", err), err)
			aiSummary = &ai.AIStudentSummary{}
			return nil
		}
		aiSummary = summary
		return nil
	})

	// Task 2: Fetch quiz scores (existing LMS DB method)
	g.Go(func() error {
		scores, err := s.GetMyQuizScores(gCtx, courseID, studentID)
		if err != nil {
			return fmt.Errorf("GetMyQuizScores: %w", err)
		}
		quizScores = scores
		return nil
	})

	// Task 3: Fetch lesson progress (new repository method)
	g.Go(func() error {
		progress, err := s.analyticsRepo.GetStudentLessonProgressSummary(gCtx, courseID, studentID)
		if err != nil {
			return fmt.Errorf("GetStudentLessonProgressSummary: %w", err)
		}
		lessonProgress = progress
		return nil
	})

	// Task 4: Fetch micro-interactions stats (new repository method)
	g.Go(func() error {
		inter, err := s.analyticsRepo.GetStudentMicroInteractionSummary(gCtx, courseID, studentID)
		if err != nil {
			return fmt.Errorf("GetStudentMicroInteractionSummary: %w", err)
		}
		interactions = inter
		return nil
	})

	// Task 5: Fetch heatmap (AI service)
	g.Go(func() error {
		hData, err := s.aiClient.GetStudentHeatmap(gCtx, studentID, courseID)
		if err != nil {
			logger.Error(fmt.Sprintf("Failed to fetch student heatmap from AI service: %v", err), err)
			heatmap = []map[string]interface{}{}
			return nil
		}
		heatmap = hData
		return nil
	})

	if err := g.Wait(); err != nil {
		return nil, err
	}

	// Combine results
	resp := &dto.StudentAnalyticsSummaryResponse{
		LessonProgress: lessonProgress,
		QuizScores:     quizScores,
		Flashcards: dto.FlashcardDetailedStats{
			TotalActive:   aiSummary.FlashcardStats.TotalActive,
			TotalMastered: aiSummary.FlashcardStats.TotalMastered,
			TotalLearning: aiSummary.FlashcardStats.TotalLearning,
			TotalNew:      aiSummary.FlashcardStats.TotalNew,
			DueToday:      aiSummary.FlashcardStats.DueToday,
			Upcoming7d:    aiSummary.FlashcardStats.Upcoming7d,
			AvgEasiness:   aiSummary.FlashcardStats.AvgEasiness,
			ReviewedToday: aiSummary.FlashcardStats.ReviewedToday,
			TotalReviews:  aiSummary.FlashcardStats.TotalReviews,
		},
		SpacedRepQuizzes: dto.SpacedRepQuizDetailedStats{
			TotalTracked: aiSummary.SpacedRepQuizStats.TotalTracked,
			DueToday:     aiSummary.SpacedRepQuizStats.DueToday,
			Mastered:     aiSummary.SpacedRepQuizStats.Mastered,
			AvgQuality:   aiSummary.SpacedRepQuizStats.AvgQuality,
		},
		MicroInteractions: interactions,
		Heatmap:           heatmap,
	}

	// Cache the result for 60s
	if s.redisCache != nil {
		if data, err := json.Marshal(resp); err == nil {
			_ = s.redisCache.Set(ctx, cacheKey, data, 60*time.Second)
		}
	}

	return resp, nil
}

func (s *AnalyticsService) GetTeacherDashboardSummary(ctx context.Context, teacherID int64) (*dto.TeacherDashboardSummaryResponse, error) {
	repoSummary, err := s.analyticsRepo.GetTeacherDashboardSummary(ctx, teacherID)
	if err != nil {
		return nil, fmt.Errorf("failed to get teacher dashboard summary: %w", err)
	}

	resp := &dto.TeacherDashboardSummaryResponse{
		TotalCoursesCount:     repoSummary.TotalCoursesCount,
		PublishedCoursesCount: repoSummary.PublishedCoursesCount,
		DraftCoursesCount:     repoSummary.DraftCoursesCount,
		TotalUniqueStudents:   repoSummary.TotalUniqueStudents,
		RegistrationTimeline:  make([]dto.RegistrationTimeline, 0, len(repoSummary.RegistrationTimeline)),
		CourseStats:          make([]dto.TeacherCourseStats, 0, len(repoSummary.CourseStats)),
	}

	for _, item := range repoSummary.RegistrationTimeline {
		resp.RegistrationTimeline = append(resp.RegistrationTimeline, dto.RegistrationTimeline{
			Date:  item.EnrollDate.Format("02/01"),
			Count: item.NewLearners,
		})
	}

	for _, item := range repoSummary.CourseStats {
		var avgQuiz *float64
		if item.AvgQuiz.Valid {
			val := item.AvgQuiz.Float64
			avgQuiz = &val
		}

		thumbnailURL := ""
		if item.ThumbnailURL.Valid {
			thumbnailURL = item.ThumbnailURL.String
		}

		resp.CourseStats = append(resp.CourseStats, dto.TeacherCourseStats{
			ID:           item.CourseID,
			Title:        item.Title,
			ThumbnailURL: thumbnailURL,
			StudentCount: item.StudentCount,
			AvgProgress:  item.AvgProgress,
			AvgQuiz:      avgQuiz,
		})
	}

	return resp, nil
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

// nfv (null float value) returns 0 for invalid NullFloat64.
func nfv(nf sql.NullFloat64) float64 {
	if nf.Valid {
		return nf.Float64
	}
	return 0
}