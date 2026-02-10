package main

import (
	"context"
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
	"example/hello/pkg/cache"
	"example/hello/pkg/database"
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

	// Initialize repositories
	userRepo := repository.NewUserRepository(db)
	courseRepo := repository.NewCourseRepository(db)
	enrollmentRepo := repository.NewEnrollmentRepository(db)
	quizRepo := repository.NewQuizRepository(db)

	// Initialize services
	userService := service.NewUserService(userRepo)
	courseService := service.NewCourseService(courseRepo, userRepo, enrollmentRepo, redisClient)
	enrollmentService := service.NewEnrollmentService(enrollmentRepo, courseRepo, userRepo)
	quizService := service.NewQuizService(quizRepo, courseRepo, userRepo)
	userSyncService := service.NewUserSyncService(userRepo)
	syncSecret := os.Getenv("LMS_SYNC_SECRET")

	// Initialize handlers
	userHandler := handler.NewUserHandler(userService)
	courseHandler := handler.NewCourseHandler(courseService)
	enrollmentHandler := handler.NewEnrollmentHandler(enrollmentService)
	fileHandler := handler.NewFileHandler(storageProvider)
	syncHandler := handler.NewUserSyncHandler(userSyncService, syncSecret)
	quizHandler := handler.NewQuizHandler(quizService, storageProvider)

	// Setup Gin router
	if cfg.App.Env == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	router := gin.New()
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

			// Protected endpoints
			protected := files.Group("")
			protected.Use(middleware.AuthMiddleware(cfg.JWT.Secret))
			{
				protected.POST("/upload", fileHandler.UploadFile)
				protected.GET("/download/*filepath", fileHandler.DownloadFile)
				protected.DELETE("/delete/*filepath", middleware.RequireRoles("ADMIN", "TEACHER"), fileHandler.DeleteFile)
			}
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
				courses.GET("/my", courseHandler.ListMyCourses)
				courses.GET("/:courseId", courseHandler.GetCourse)

				// Teacher/Admin only - Create course
				courses.POST("", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.CreateCourse)

				// Teacher/Admin only - Update/Delete/Publish course
				courses.PUT("/:courseId", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.UpdateCourse)
				courses.DELETE("/:courseId", middleware.RequireRole("ADMIN"), courseHandler.DeleteCourse)
				courses.POST("/:courseId/publish", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.PublishCourse)

				// Section management (Owner/Admin only via service layer)
				courses.POST("/:courseId/sections", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.CreateSection)
				courses.GET("/:courseId/sections", courseHandler.ListSections)
			}

			// SECTION MANAGEMENT
			sections := auth.Group("/sections")
			{
				sections.GET("/:sectionId", courseHandler.GetSection)
				sections.PUT("/:sectionId", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.UpdateSection)
				sections.DELETE("/:sectionId", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.DeleteSection)

				// Content management
				sections.POST("/:sectionId/content", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.CreateContent)
				sections.GET("/:sectionId/content", courseHandler.ListContent)
			}

			// CONTENT MANAGEMENT
			content := auth.Group("/content")
			{
				content.GET("/:contentId", courseHandler.GetContent)
				content.PUT("/:contentId", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.UpdateContent)
				content.DELETE("/:contentId", middleware.RequireRoles("ADMIN", "TEACHER"), courseHandler.DeleteContent)
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

			// Course learners management
			courses.GET("/:courseId/learners", enrollmentHandler.GetCourseLearners)
			courses.POST("/:courseId/bulk-enroll", middleware.RequireRoles("ADMIN", "TEACHER"), enrollmentHandler.BulkEnroll)
		
			quizzes := auth.Group("/quizzes")
			{
				// Teacher/Admin - Quiz CRUD
				quizzes.POST("", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.CreateQuiz)
				quizzes.GET("/:quizId", quizHandler.GetQuiz)
				quizzes.PUT("/:quizId", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.UpdateQuiz)
				quizzes.DELETE("/:quizId", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.DeleteQuiz)

				// Question Management
				quizzes.POST("/:quizId/questions", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.CreateQuestion)
				quizzes.GET("/:quizId/questions", quizHandler.ListQuestions)

				// Student - Take Quiz
				quizzes.POST("/:quizId/start", quizHandler.StartQuizAttempt)
				quizzes.GET("/:quizId/my-attempts", quizHandler.GetMyQuizAttempts)

				// Grading
				quizzes.GET("/:quizId/grading", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.ListAnswersForGrading)
				quizzes.POST("/:quizId/bulk-grade", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.BulkGrade)
			}

			// QUESTION ROUTES
			questions := auth.Group("/questions")
			{
				questions.PUT("/:questionId", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.UpdateQuestion)
				questions.DELETE("/:questionId", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.DeleteQuestion)
				
				questions.POST("/:questionId/images", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.UploadQuestionImage)
				questions.GET("/:questionId/images", quizHandler.ListQuestionImages)
				questions.DELETE("/:questionId/images/:imageId", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.DeleteQuestionImage)
			}

			// QUIZ ATTEMPT ROUTES
			attempts := auth.Group("/attempts")
			{
				attempts.POST("/:attemptId/answers", quizHandler.SubmitAnswer)
				attempts.POST("/:attemptId/submit", quizHandler.SubmitQuiz)
				attempts.GET("/:attemptId/result", quizHandler.GetQuizResult)
				attempts.GET("/:attemptId/review", quizHandler.ReviewQuiz)
				attempts.GET("/:attemptId/summary", quizHandler.GetAttemptSummary)
			}

			// ANSWER GRADING ROUTES
			answers := auth.Group("/answers")
			{
				answers.POST("/:answerId/grade", middleware.RequireRoles("ADMIN", "TEACHER"), quizHandler.GradeAnswer)
			}
		}
	}

	// Start server
	srv := &http.Server{
		Addr:         fmt.Sprintf(":%s", cfg.App.Port),
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
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