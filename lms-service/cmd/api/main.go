package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"example/hello/internal/config"
	"example/hello/internal/handler"
	"example/hello/internal/middleware"
	"example/hello/internal/repository"
	"example/hello/internal/service"
	"example/hello/pkg/ai"
	"example/hello/pkg/cache"
	"example/hello/pkg/database"
	"example/hello/pkg/kafka"
	"example/hello/pkg/logger"
	"example/hello/pkg/storage"

	"github.com/gin-gonic/gin"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"

	// Import generated swagger docs
	_ "example/hello/docs"
)

// @title LMS API Documentation
// @version 1.0
// @description This is the API documentation for LMS (Learning Management System)
// @termsOfService https://bdc.hpcc.vn/terms

// @contact.name API Support
// @contact.url https://bdc.hpcc.vn/support
// @contact.email support@bdc.hpcc.vn

// @license.name Apache 2.0
// @license.url http://www.apache.org/licenses/LICENSE-2.0.html

// @host localhost:3000
// @BasePath /lmsapiv1

// @securityDefinitions.apikey BearerAuth
// @in header
// @name Authorization
// @description Type "Bearer" followed by a space and JWT token.

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatal("Failed to load config:", err)
	}

	// Initialize logger
	logger.Init(cfg.App.Env)

	// Initialize database
	db, err := database.NewPostgresDB(cfg.Database)
	if err != nil {
		logger.Fatal("Failed to connect to database", err)
	}
	defer db.Close()

	// Initialize Redis cache
	redisClient, err := cache.NewRedisClient(cfg.Redis)
	if err != nil {
		logger.Fatal("Failed to connect to Redis", err)
	}
	defer redisClient.Close()

	// Initialize storage
	storageCfg := config.LoadStorageConfig()
	var storageProvider storage.Storage

	if storageCfg.Type == "minio" {
		storageProvider, err = storage.NewMinIOStorage(storageCfg)
		if err != nil {
			logger.Fatal("Failed to initialize MinIO storage", err)
		}
		logger.Info("Using MinIO storage")
	} else {
		storageProvider, err = storage.NewLocalStorage(storageCfg.LocalBasePath)
		if err != nil {
			logger.Fatal("Failed to initialize local storage", err)
		}
		logger.Info("Using local storage")
	}

	aiClient := ai.NewClient()

	// Initialize repositories
	userRepo := repository.NewUserRepository(db)
	courseRepo := repository.NewCourseRepository(db)
	enrollmentRepo := repository.NewEnrollmentRepository(db)
	quizRepo := repository.NewQuizRepository(db)
	forumRepo := repository.NewForumRepository(db)
	progressRepo := repository.NewProgressRepository(db)
	analyticsRepo := repository.NewAnalyticsRepository(db)

	flashcardRepo := repository.NewFlashcardRepository(db)

	kafka.InitProducer()
	defer kafka.CloseProducer()

	go kafka.StartConsumer(context.Background(), func(ctx context.Context, event kafka.ProcessDocumentStatusEvent) error {
		logger.Info(fmt.Sprintf("Received status update for content %d: %s", event.ContentID, event.Status))
		if event.Status == "completed" || event.Status == "success" {
			event.Status = "indexed"
		}
		return courseRepo.UpdateContentAIIndexStatus(ctx, event.ContentID, event.Status)
	})

	go kafka.StartAIJobStatusConsumer(context.Background(), func(ctx context.Context, event kafka.AIJobStatusEvent) error {
		logger.Info(fmt.Sprintf("Received AI job status for %s: %s", event.JobID, event.Status))
		// Serialize and store into Redis
		data, _ := json.Marshal(event)
		redisKey := "ai_job:" + event.JobID
		return redisClient.Set(ctx, redisKey, data, 24*time.Hour) // Keep for 24 hours
	})

	// Initialize services. Services that benefit from caching (read-heavy CRUD
	// paths) receive the shared *cache.RedisCache; each service builds its own
	// singleflight-backed Loader internally so cache stampedes on hot keys
	// only ever produce one DB query per process.
	userService := service.NewUserService(userRepo, redisClient)
	courseService := service.NewCourseService(courseRepo, userRepo, enrollmentRepo, redisClient)
	enrollmentService := service.NewEnrollmentService(enrollmentRepo, courseRepo, userRepo, progressRepo, redisClient)
	quizService := service.NewQuizService(quizRepo, courseRepo, userRepo, progressRepo, aiClient)
	userSyncService := service.NewUserSyncService(userRepo, redisClient)
	forumService := service.NewForumService(forumRepo, courseRepo)
	syncSecret := os.Getenv("LMS_SYNC_SECRET")
	progressService := service.NewProgressService(progressRepo, enrollmentRepo, redisClient)
	analyticsService := service.NewAnalyticsService(analyticsRepo, courseRepo, enrollmentRepo, aiClient)
	flashcardService := service.NewFlashcardService(flashcardRepo, aiClient, redisClient)

	// Initialize handlers
	userHandler := handler.NewUserHandler(userService)
	courseHandler := handler.NewCourseHandler(courseService)
	enrollmentHandler := handler.NewEnrollmentHandler(enrollmentService)
	fileHandler := handler.NewFileHandler(storageProvider, cfg.Upload)
	syncHandler := handler.NewUserSyncHandler(userSyncService, syncSecret)
	quizHandler := handler.NewQuizHandler(quizService, storageProvider)
	forumHandler := handler.NewForumHandler(forumService)
	progressHandler := handler.NewProgressHandler(progressService)
	analyticsHandler := handler.NewAnalyticsHandler(analyticsService, aiClient)
	aiHandler := handler.NewAIHandler(aiClient, courseRepo, quizRepo, redisClient)
	flashcardHandler := handler.NewFlashcardHandler(flashcardService, enrollmentService)

	// Setup Gin router
	if cfg.App.Env == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	router := gin.New()
	router.MaxMultipartMemory = 64 << 20 // 64 MB
	router.Use(gin.Recovery())
	router.Use(middleware.Logger())
	router.Use(middleware.CORS(cfg.CORS))
	router.Use(middleware.RateLimit(redisClient))

	// Health check
	healthHandler := func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":  "healthy",
			"time":    time.Now(),
			"version": cfg.App.Version,
		})
	}
	router.GET("/health", healthHandler)
	router.HEAD("/health", healthHandler)

	// Swagger documentation with dynamic URL configuration
	// Development: http://localhost:3000/lmsapidocs/swagger/index.html
	// Production: https://bdc.hpcc.vn/lmsapidocs/swagger/index.html
	swaggerURL := "/lmsapidocs/swagger/doc.json"

	router.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerFiles.Handler,
		ginSwagger.URL(swaggerURL),
		ginSwagger.DefaultModelsExpandDepth(-1),
		ginSwagger.PersistAuthorization(true),
	))

	// API v1 routes
	v1 := router.Group("/api/v1")
	{
		// SYNC ROUTES
		sync := v1.Group("/sync")
		sync.Use(syncHandler.SyncSecret())
		{
			sync.POST("/user", syncHandler.SyncUser)
			sync.POST("/users/bulk", syncHandler.BulkSyncUsers)
			sync.DELETE("/user/:userId", syncHandler.DeleteUser)
		}

		// FILE SERVING - Public access (no auth needed for viewing)
		files := v1.Group("/files")
		{
			// Public file serving endpoint
			files.GET("/serve/*filepath", fileHandler.ServeFile)
			files.GET("/download/*filepath", fileHandler.DownloadFile)

			// Protected endpoints - require authentication
			// 1. Flexible endpoints (Internal Service Secret OR JWT)
			flexible := files.Group("")
			flexible.Use(middleware.ServiceOrAuthMiddleware(cfg.JWT.Secret, cfg.AIConf.Secret))
			{
				flexible.GET("/presigned/*filepath", fileHandler.GetPresignedURL)
			}

			// 2. Strict protected endpoints (JWT ONLY)
			protected := files.Group("")
			protected.Use(middleware.AuthMiddleware(cfg.JWT.Secret))
			{
				protected.POST("/upload", fileHandler.UploadFile)
				protected.DELETE("/delete/*filepath", fileHandler.DeleteFile)
			}
		}

		// ── Section management (Internal Service Secret OR JWT) ──────────────
		// AI service calls these endpoints using X-API-Secret header.
		// Normal users continue to use JWT authentication.
		flexCourses := v1.Group("/courses")
		flexCourses.Use(middleware.ServiceOrAuthMiddleware(cfg.JWT.Secret, cfg.AIConf.Secret))
		{
			flexCourses.POST("/:courseId/sections", courseHandler.CreateSection)
			flexCourses.GET("/:courseId/sections", courseHandler.ListSections)
			flexCourses.GET("/my", courseHandler.ListMyCourses)
		}

		// Protected routes - require authentication
		auth := v1.Group("")
		auth.Use(middleware.AuthMiddleware(cfg.JWT.Secret))
		{
			// User role management
			auth.GET("/me/roles", userHandler.GetMyRoles)

			// COURSE MANAGEMENT
			courses := auth.Group("/courses")
			{
				// Public course routes (anyone authenticated can view published courses)
				courses.GET("", courseHandler.ListPublishedCourses)
				courses.GET("/:courseId", courseHandler.GetCourse)

				// Teacher/Admin only - Create course
				courses.POST("", courseHandler.CreateCourse)

				// Teacher/Admin only - Update/Delete/Publish course
				courses.PUT("/:courseId", courseHandler.UpdateCourse)
				courses.DELETE("/:courseId", middleware.RequireRole("ADMIN"), courseHandler.DeleteCourse)
				courses.POST("/:courseId/publish", courseHandler.PublishCourse)

				// ── Analytics (Teacher / Admin only)
				courses.GET("/:courseId/quiz-analytics", analyticsHandler.GetCourseQuizAnalytics)
				courses.GET("/:courseId/student-progress-overview", analyticsHandler.GetStudentProgressOverview)

				// Course learners management
				courses.GET("/:courseId/learners", enrollmentHandler.GetCourseLearners)
				courses.POST("/:courseId/bulk-enroll", enrollmentHandler.BulkEnroll)

				// ── Analytics (Student) ───────────────────────────────────
				courses.GET("/:courseId/my-quiz-scores", analyticsHandler.GetMyQuizScores)
				courses.GET("/:courseId/analytics/weaknesses", analyticsHandler.GetStudentWeaknesses)
				courses.GET("/:courseId/analytics/flashcard-stats", analyticsHandler.GetFlashcardStats)

				// ── Flashcards (Student) ──────────────────────────────────
				courses.POST("/:courseId/nodes/:nodeId/flashcards/generate", flashcardHandler.GenerateFlashcards)
				courses.GET("/:courseId/flashcards/due", flashcardHandler.ListDueFlashcards)
				courses.GET("/:courseId/nodes/:nodeId/flashcards", flashcardHandler.ListFlashcardsByNode)

				// ── Progress tracking (Student) ───────────────────────────
				courses.GET("/:courseId/my-progress", progressHandler.GetMyProgress)
				courses.GET("/:courseId/progress-detail", progressHandler.GetMyProgressDetail)
			}

			// FLASHCARD ROUTE (Outside course root context)
			flashcards := auth.Group("/flashcards")
			{
				flashcards.POST("/:flashcardId/review", flashcardHandler.ReviewFlashcard)
			}

			// SECTION MANAGEMENT
			sections := auth.Group("/sections")
			{
				sections.GET("/:sectionId", courseHandler.GetSection)
				sections.PUT("/:sectionId", courseHandler.UpdateSection)
				sections.DELETE("/:sectionId", courseHandler.DeleteSection)

				// Content management
				sections.POST("/:sectionId/content", courseHandler.CreateContent)
				sections.GET("/:sectionId/content", courseHandler.ListContent)
			}

			// CONTENT MANAGEMENT
			content := auth.Group("/content")
			{
				content.GET("/:contentId", courseHandler.GetContent)
				content.GET("/:contentId/quiz", quizHandler.GetQuizByContentID)
				content.PUT("/:contentId", courseHandler.UpdateContent)
				content.DELETE("/:contentId", courseHandler.DeleteContent)
				// ── Progress tracking (Student) ───────────────────────────
				content.POST("/:contentId/complete", progressHandler.MarkComplete)
				content.POST("/:contentId/process", aiHandler.TriggerDocumentProcess)

				content.POST("/:contentId/ai-index", aiHandler.TriggerContentAutoIndex)
				content.GET("/:contentId/ai-index-status", aiHandler.GetContentAutoIndexStatus)
			}

			// ENROLLMENT MANAGEMENT
			enrollments := auth.Group("/enrollments")
			{
				// Student enrollment
				enrollments.POST("", enrollmentHandler.EnrollCourse)
				enrollments.GET("/my", enrollmentHandler.GetMyEnrollments)
				enrollments.DELETE("/:enrollmentId", enrollmentHandler.CancelEnrollment)

				// Teacher approval/rejection
				enrollments.PUT("/:enrollmentId/accept", enrollmentHandler.AcceptEnrollment)
				enrollments.PUT("/:enrollmentId/reject", enrollmentHandler.RejectEnrollment)
			}

			quizzes := auth.Group("/quizzes")
			{
				// Teacher/Admin - Quiz CRUD
				quizzes.POST("", quizHandler.CreateQuiz)
				quizzes.GET("/:quizId", quizHandler.GetQuiz)
				quizzes.PUT("/:quizId", quizHandler.UpdateQuiz)
				quizzes.DELETE("/:quizId", quizHandler.DeleteQuiz)

				// Question Management
				quizzes.POST("/:quizId/questions", quizHandler.CreateQuestion)
				quizzes.GET("/:quizId/questions", quizHandler.ListQuestions)

				// Student - Take Quiz
				quizzes.POST("/:quizId/start", quizHandler.StartQuizAttempt)
				quizzes.GET("/:quizId/my-attempts", quizHandler.GetMyQuizAttempts)

				// Grading
				quizzes.GET("/:quizId/grading", quizHandler.ListAnswersForGrading)
				quizzes.POST("/:quizId/bulk-grade", quizHandler.BulkGrade)
				quizzes.GET("/:quizId/all-attempts", analyticsHandler.GetQuizAllAttempts)
				quizzes.GET("/:quizId/wrong-answer-stats", analyticsHandler.GetQuizWrongAnswerStats)
			}

			// QUESTION ROUTES
			questions := auth.Group("/questions")
			{
				questions.PUT("/:questionId", quizHandler.UpdateQuestion)
				questions.DELETE("/:questionId", quizHandler.DeleteQuestion)

				questions.POST("/:questionId/images", quizHandler.UploadQuestionImage)
				questions.GET("/:questionId/images", quizHandler.ListQuestionImages)
				questions.DELETE("/:questionId/images/:imageId", quizHandler.DeleteQuestionImage)
			}

			// QUIZ ATTEMPT ROUTES
			attempts := auth.Group("/attempts")
			{
				attempts.GET("/:attemptId/answers", quizHandler.GetAttemptAnswers)
				attempts.POST("/:attemptId/answers", quizHandler.SubmitAnswer)
				attempts.POST("/:attemptId/submit", quizHandler.SubmitQuiz)
				attempts.GET("/:attemptId/result", quizHandler.GetQuizResult)
				attempts.GET("/:attemptId/review", quizHandler.ReviewQuiz)
				attempts.GET("/:attemptId/summary", quizHandler.GetAttemptSummary)
			}

			// ANSWER GRADING ROUTES
			answers := auth.Group("/answers")
			{
				answers.POST("/:answerId/grade", quizHandler.GradeAnswer)
			}

			// FORUM ROUTES
			// Forum posts on content
			content.POST("/:contentId/forum/posts", forumHandler.CreatePost)
			content.GET("/:contentId/forum/posts", forumHandler.ListPosts)

			// Individual forum posts
			forum := auth.Group("/forum")
			{
				// Post operations
				posts := forum.Group("/posts")
				{
					posts.GET("/:postId", forumHandler.GetPost)
					posts.PUT("/:postId", middleware.RequireRoles("STUDENT", "TEACHER", "ADMIN"), forumHandler.UpdatePost)
					posts.DELETE("/:postId", middleware.RequireRoles("STUDENT", "TEACHER", "ADMIN"), forumHandler.DeletePost)

					// Admin/Teacher actions
					posts.POST("/:postId/pin", middleware.RequireRoles("TEACHER", "ADMIN"), forumHandler.PinPost)
					posts.POST("/:postId/lock", middleware.RequireRoles("TEACHER", "ADMIN"), forumHandler.LockPost)

					// Voting
					posts.POST("/:postId/vote", forumHandler.VotePost)

					// Comments on posts
					posts.POST("/:postId/comments", forumHandler.CreateComment)
					posts.GET("/:postId/comments", forumHandler.ListComments)
				}

				// Comment operations
				comments := forum.Group("/comments")
				{
					comments.PUT("/:commentId", middleware.RequireRoles("STUDENT", "TEACHER", "ADMIN"), forumHandler.UpdateComment)
					comments.DELETE("/:commentId", middleware.RequireRoles("STUDENT", "TEACHER", "ADMIN"), forumHandler.DeleteComment)
					comments.POST("/:commentId/accept", forumHandler.AcceptComment)
					comments.POST("/:commentId/vote", forumHandler.VoteComment)
				}
			}

			aiGroup := auth.Group("/ai")
			{
				// ── Phase 1: Error Diagnosis ──────────────────────────────────────────
				// POST /api/v1/ai/attempts/:attemptId/questions/:questionId/diagnose
				aiGroup.POST("/attempts/:attemptId/questions/:questionId/diagnose",
					aiHandler.DiagnoseWrongAnswer)
				aiGroup.GET("/knowledge-graph/global", 
					aiHandler.GetGlobalKnowledgeGraph)
				aiGroup.POST("/knowledge-graph/link-global",
					aiHandler.TriggerGlobalLinking)
				
				// System-wide Polling Endpoint for AI Jobs
				aiGroup.GET("/jobs/:jobId/status",
					aiHandler.GetJobStatus())
			}

			// Per-course AI routes (reuse courseId param)
			aiCourses := auth.Group("/courses/:courseId/ai")
			{
				// ── Phase 1: Heatmap ──────────────────────────────────────────────────
				aiCourses.GET("/heatmap",
					middleware.RequireRoles("ADMIN", "TEACHER"),
					aiHandler.GetClassHeatmap)

				aiCourses.GET("/my-heatmap",
					aiHandler.GetStudentHeatmap)

				// ── Knowledge Graph ───────────────────────────────────────────────────
				aiCourses.POST("/nodes",
					middleware.RequireRoles("ADMIN", "TEACHER"),
					aiHandler.CreateKnowledgeNode)

				aiCourses.GET("/nodes",
					aiHandler.ListKnowledgeNodes)

				// ── Phase 2: Quiz Generation ──────────────────────────────────────────
				aiCourses.POST("/generate-quiz",
					middleware.RequireRoles("ADMIN", "TEACHER"),
					aiHandler.GenerateQuiz)

				aiCourses.GET("/drafts",
					middleware.RequireRoles("ADMIN", "TEACHER"),
					aiHandler.ListDraftQuestions)

				// ── Phase 2: Spaced Repetition ────────────────────────────────────────
				aiCourses.GET("/reviews/due",
					aiHandler.GetDueReviews)

				aiCourses.POST("/reviews/record",
					aiHandler.RecordReviewResponse)

				aiCourses.GET("/reviews/stats",
					aiHandler.GetReviewStats)

				aiCourses.GET("/knowledge-graph", aiHandler.GetCourseKnowledgeGraph)

				aiCourses.GET("/nodes/:nodeId/chunks", aiHandler.GetNodeChunks)
				aiCourses.DELETE("/nodes/:nodeId", aiHandler.DeleteKnowledgeNode)
			}

			// Quiz draft review (outside course context)
			quizDrafts := auth.Group("/ai/quiz-drafts")
			{
				quizDrafts.POST("/:genId/approve",
					middleware.RequireRoles("ADMIN", "TEACHER"),
					aiHandler.ApproveQuestion)

				quizDrafts.POST("/:genId/reject",
					middleware.RequireRoles("ADMIN", "TEACHER"),
					aiHandler.RejectQuestion)
			}
		}
	}

	// Start server
	srv := &http.Server{
		Addr:              fmt.Sprintf(":%s", cfg.App.Port),
		Handler:           router,
		ReadHeaderTimeout: 20 * time.Second,
		ReadTimeout:       cfg.Server.ReadTimeout,  // Sử dụng từ config (10 phút)
		WriteTimeout:      cfg.Server.WriteTimeout, // Sử dụng từ config (10 phút)
		IdleTimeout:       cfg.Server.IdleTimeout,
	}

	// Graceful shutdown
	go func() {
		logger.Info(fmt.Sprintf("Starting LMS server on port %s", cfg.App.Port))
		logger.Info(fmt.Sprintf("Environment: %s", cfg.App.Env))

		if cfg.App.Env == "production" {
			logger.Info("Swagger docs: https://bdc.hpcc.vn/lmsapidocs/swagger/index.html")
			logger.Info("Mock JWT: https://bdc.hpcc.vn/lmsapidocs/mock-jwt")
		} else {
			logger.Info("Swagger docs: http://localhost:3000/lmsapidocs/swagger/index.html")
			logger.Info("Mock JWT: http://localhost:3000/lmsapidocs/mock-jwt")
		}

		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("Failed to start server", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		logger.Fatal("Server forced to shutdown", err)
	}

	logger.Info("Server exited")
}
