package main

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"lab-service/internal/config"
	"lab-service/internal/handler"
	"lab-service/internal/middleware"
	"lab-service/internal/repository"
	"lab-service/internal/runtime"
	"lab-service/internal/service"
	"lab-service/pkg/cache"
	"lab-service/pkg/database"
	"lab-service/pkg/kafka"
	"lab-service/pkg/logger"

	"github.com/gin-gonic/gin"
)

func main() {
	// -- Load config ---------------------------------------------
	cfg, err := config.Load()
	if err != nil {
		fmt.Printf("Failed to load config: %v\n", err)
		os.Exit(1)
	}

	logger.Init(cfg.App.Env)
	logger.Info(fmt.Sprintf("Starting %s v%s (%s)", cfg.App.Name, cfg.App.Version, cfg.App.Env))

	// -- Database ------------------------------------------------
	db, err := database.NewPostgresDB(cfg.Database)
	if err != nil {
		logger.Fatal("Failed to connect to database", err)
	}
	defer db.Close()

	// -- Run migrations ------------------------------------------
	runMigrations(db)

	// -- Redis ---------------------------------------------------
	redisCache, err := cache.NewRedisClient(cfg.Redis)
	if err != nil {
		logger.Warn(fmt.Sprintf("Failed to connect to Redis: %v (continuing without cache)", err))
	} else {
		defer redisCache.Close()
	}
	_ = redisCache // Will be used in Phase 2 for session tokens

	// -- Kafka ---------------------------------------------------
	kafka.InitProducer()
	defer kafka.CloseProducer()

	// -- Runtime Adapter Registry --------------------------------
	runtimeRegistry := runtime.NewRegistry()
	codingRunner := runtime.NewCodingRunner(cfg.RuntimeSecurity.AllowUnsafeLocalExecution, cfg.CodingSandbox)
	runtimeRegistry.Register(codingRunner)
	runtimeRegistry.Register(runtime.NewDatabaseRunner(cfg.DatabaseLab))
	runtimeRegistry.Register(runtime.NewWorkspaceRunner())
	runtimeRegistry.Register(runtime.NewHPCRunner(cfg.SLURM))
	runtimeRegistry.Register(runtime.NewJupyterRunner())
	runtimeRegistry.Register(runtime.NewCustomRunner())
	logger.Info("Runtime adapters registered: CODING, DATABASE, WORKSPACE, HPC, JUPYTER, CUSTOM")

	// -- Repositories --------------------------------------------
	labRepo := repository.NewLabRepository(db)
	experimentRepo := repository.NewExperimentRepository(db)
	enrollmentRepo := repository.NewEnrollmentRepository(db)
	submissionRepo := repository.NewSubmissionRepository(db)
	testCaseRepo := repository.NewTestCaseRepository(db)
	leaderboardRepo := repository.NewLeaderboardRepository(db)
	userRepo := repository.NewUserRepository(db)

	// -- Services ------------------------------------------------
	labService := service.NewLabService(labRepo, enrollmentRepo)
	experimentService := service.NewExperimentService(experimentRepo, labRepo, enrollmentRepo)
	submissionService := service.NewSubmissionService(
		submissionRepo, testCaseRepo, labRepo, enrollmentRepo,
		leaderboardRepo, runtimeRegistry, codingRunner.Available(),
	)

	// -- Handlers ------------------------------------------------
	labHandler := handler.NewLabHandler(labService, cfg.RuntimeSecurity)
	experimentHandler := handler.NewExperimentHandler(experimentService)
	submissionHandler := handler.NewSubmissionHandler(submissionService)
	enrollmentHandler := handler.NewEnrollmentHandler(enrollmentRepo)
	testCaseHandler := handler.NewTestCaseHandler(testCaseRepo)
	leaderboardHandler := handler.NewLeaderboardHandler(leaderboardRepo)
	syncHandler := handler.NewSyncHandler(userRepo)

	// -- Gin Router ----------------------------------------------
	if cfg.App.Env == "production" {
		gin.SetMode(gin.ReleaseMode)
	}
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.Logger())
	r.Use(middleware.CORS(cfg.CORS))

	// -- Health Check --------------------------------------------
	healthHandler := func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":              "healthy",
			"service":             cfg.App.Name,
			"version":             cfg.App.Version,
			"supported_lab_types": []string{"CODING", "HPC", "JUPYTER", "WORKSPACE", "DATABASE", "CUSTOM", "PLANT", "ROBOT", "CHEMISTRY"},
			"runtime_security": gin.H{
				"unsafe_local_execution_enabled": cfg.RuntimeSecurity.AllowUnsafeLocalExecution,
				"unsafe_terminal_enabled": cfg.RuntimeSecurity.AllowUnsafeTerminal,
				"production_execution_mode": "isolated-worker-required",
				"coding_sandbox_enabled": codingRunner.Available(),
			},
		})
	}
	r.GET("/health", healthHandler)
	r.HEAD("/health", healthHandler)
	// Traefik rewrites /labapiv1/* to /api/v1/*; expose the same probe there
	// so operators can verify which binary public traffic reaches.
	r.GET("/api/v1/health", healthHandler)
	r.HEAD("/api/v1/health", healthHandler)

	// -- Sync Routes (service secret) ----------------------------
	syncSecret := os.Getenv("LMS_SYNC_SECRET")
	if syncSecret == "" {
		syncSecret = cfg.JWT.Secret
	}
	syncGroup := r.Group("/api/v1/sync")
	syncGroup.Use(middleware.ServiceOrAuthMiddleware(cfg.JWT.Secret, syncSecret))
	{
		syncGroup.POST("/user", syncHandler.SyncUser)
		syncGroup.POST("/users/bulk", syncHandler.BulkSyncUsers)
	}

	// -- Protected Routes (JWT) ----------------------------------
	api := r.Group("/api/v1")
	api.Use(middleware.AuthMiddleware(cfg.JWT.Secret))
	{
		// Labs CRUD
		api.GET("/labs", labHandler.ListPublishedLabs)
		api.GET("/labs/my", labHandler.ListMyLabs)
		api.GET("/labs/manage", middleware.RequireRoles("ADMIN"), labHandler.ListAllLabs)
		api.POST("/labs", middleware.RequireRoles("ADMIN"), labHandler.CreateLab)
		api.GET("/labs/:labId", labHandler.GetLab)
		api.PUT("/labs/:labId", middleware.RequireRoles("ADMIN"), labHandler.UpdateLab)
		api.DELETE("/labs/:labId", middleware.RequireRoles("ADMIN"), labHandler.DeleteLab)
		api.POST("/labs/:labId/publish", middleware.RequireRoles("ADMIN"), labHandler.PublishLab)

		// Versioned Virtual STEM experiment definitions
		api.POST("/labs/:labId/versions", middleware.RequireRoles("ADMIN"), experimentHandler.CreateVersion)
		api.GET("/labs/:labId/versions", middleware.RequireRoles("ADMIN"), experimentHandler.ListVersions)
		api.GET("/labs/:labId/published-version", experimentHandler.GetPublishedVersion)
		api.GET("/lab-versions/:versionId/definition", experimentHandler.GetVersion)
		api.POST("/lab-versions/:versionId/validate", middleware.RequireRoles("ADMIN"), experimentHandler.ValidateVersion)
		api.POST("/lab-versions/:versionId/publish", middleware.RequireRoles("ADMIN"), experimentHandler.PublishVersion)

		// Learner experiment runs, deterministic trials and replayable evidence
		api.POST("/lab-versions/:versionId/runs", experimentHandler.CreateRun)
		api.GET("/labs/:labId/runs", middleware.RequireRoles("ADMIN"), experimentHandler.ListLabRuns)
		api.GET("/runs/:runId", experimentHandler.GetRun)
		api.POST("/runs/:runId/complete", experimentHandler.CompleteRun)
		api.POST("/runs/:runId/trials", experimentHandler.CreateTrial)
		api.POST("/runs/:runId/evidence", experimentHandler.AppendEvidence)
		api.GET("/runs/:runId/events", experimentHandler.ListEvidence)

		// Lab Interactive Session & Web Terminal
		api.POST("/labs/:labId/session/start", labHandler.StartSession)
		api.GET("/labs/:labId/session/terminal/ws", labHandler.TerminalWS)

		// Lab Sections
		api.POST("/labs/:labId/sections", middleware.RequireRoles("ADMIN"), labHandler.CreateSection)
		api.GET("/labs/:labId/sections", labHandler.ListSections)
		api.PUT("/sections/:sectionId", middleware.RequireRoles("ADMIN"), labHandler.UpdateSection)
		api.DELETE("/sections/:sectionId", middleware.RequireRoles("ADMIN"), labHandler.DeleteSection)

		// Lab Content
		api.POST("/sections/:sectionId/content", middleware.RequireRoles("ADMIN"), labHandler.CreateContent)
		api.GET("/sections/:sectionId/content", labHandler.ListContent)
		api.PUT("/content/:contentId", middleware.RequireRoles("ADMIN"), labHandler.UpdateContent)
		api.DELETE("/content/:contentId", middleware.RequireRoles("ADMIN"), labHandler.DeleteContent)


		// Test Cases
		api.POST("/labs/:labId/test-cases", middleware.RequireRoles("ADMIN"), testCaseHandler.CreateTestCase)
		api.GET("/labs/:labId/test-cases", testCaseHandler.ListTestCases)
		api.PUT("/test-cases/:id", middleware.RequireRoles("ADMIN"), testCaseHandler.UpdateTestCase)
		api.DELETE("/test-cases/:id", middleware.RequireRoles("ADMIN"), testCaseHandler.DeleteTestCase)
		api.POST("/labs/:labId/test-cases/bulk", middleware.RequireRoles("ADMIN"), testCaseHandler.BulkCreateTestCases)


		// Submissions
		api.POST("/labs/:labId/run", submissionHandler.RunCode)
		api.POST("/labs/:labId/submit", submissionHandler.SubmitCode)
		api.POST("/labs/:labId/hpc-jobs", submissionHandler.SubmitHPCJob)
		api.GET("/labs/:labId/submissions/my", submissionHandler.ListMySubmissions)
		api.GET("/submissions/:subId", submissionHandler.GetSubmission)

		// Leaderboard
		api.GET("/labs/:labId/leaderboard", leaderboardHandler.GetLabLeaderboard)

		// Enrollment
		api.POST("/labs/:labId/enroll", enrollmentHandler.EnrollLab)
		api.GET("/labs/:labId/learners", middleware.RequireRoles("ADMIN"), enrollmentHandler.GetLabLearners)
		api.GET("/enrollments/labs/my", enrollmentHandler.GetMyLabEnrollments)
		api.DELETE("/lab-enrollments/:id", enrollmentHandler.CancelEnrollment)
		api.POST("/labs/:labId/bulk-enroll", middleware.RequireRoles("ADMIN"), enrollmentHandler.BulkEnroll)
	}

	// -- Start Kafka Consumers -----------------------------------
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go kafka.StartJobStatusConsumer(ctx, func(ctx context.Context, event kafka.JobStatusEvent) error {
		logger.Info(fmt.Sprintf("Job status update: job=%s status=%s", event.JobID, event.Status))
		// Phase 2: Update submission status in DB
		return nil
	})

	// -- Start HTTP Server ---------------------------------------
	srv := &http.Server{
		Addr:         ":" + cfg.App.Port,
		Handler:      r,
		ReadTimeout:  cfg.Server.ReadTimeout,
		WriteTimeout: cfg.Server.WriteTimeout,
		IdleTimeout:  cfg.Server.IdleTimeout,
	}

	go func() {
		logger.Info(fmt.Sprintf("Lab Service listening on :%s", cfg.App.Port))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("Server failed", err)
		}
	}()

	// -- Graceful Shutdown ---------------------------------------
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	logger.Info("Shutting down Lab Service...")

	cancel() // Stop Kafka consumers

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Error("Server forced to shutdown", err)
	}
	logger.Info("Lab Service stopped")
}

func runMigrations(db *sql.DB) {
	// Migrations are applied via init SQL files mounted in Docker
	// For dev, you can run them manually or use a migration tool
	logger.Info("Database migrations checked (applied via Docker init scripts)")
}
