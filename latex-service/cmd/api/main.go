package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"latex-service/internal/compiler"
	"latex-service/internal/config"
	"latex-service/internal/handler"
	"latex-service/internal/middleware"
	"latex-service/internal/repository"
	"latex-service/internal/service"
	pkgauth "latex-service/pkg/auth"
	"latex-service/pkg/cache"
	"latex-service/pkg/database"
	"latex-service/pkg/logger"
	"latex-service/pkg/storage"

	"github.com/gin-gonic/gin"
)

func main() {
	// 1. Load config
	cfg, err := config.Load()
	if err != nil {
		fmt.Printf("Failed to load config: %v\n", err)
		os.Exit(1)
	}

	// 2. Initialize logger
	logger.Init(cfg.App.Env)
	logger.Info("Starting LaTeX Service...")

	// 3. Initialize Postgres DB
	db, err := database.NewPostgresDB(cfg.Database)
	if err != nil {
		logger.Fatal("Failed to initialize database", err)
	}
	defer db.Close()
	logger.Info("Connected to PostgreSQL database")

	// 4. Initialize Redis
	redisCache, err := cache.NewRedisClient(cfg.Redis)
	if err != nil {
		logger.Fatal("Failed to initialize Redis", err)
	}
	logger.Info("Connected to Redis")

	// 5. Initialize Storage
	var store storage.Storage
	if cfg.Storage.Type == "minio" {
		store, err = storage.NewMinIOStorage(cfg.Storage)
		if err != nil {
			logger.Fatal("Failed to initialize MinIO", err)
		}
		logger.Info(fmt.Sprintf("Initialized MinIO storage (bucket: %s)", cfg.Storage.MinIOBucket))
	} else {
		logger.Fatal("Unsupported storage type: "+cfg.Storage.Type, nil)
	}

	// 6. Initialize Repositories
	projectRepo := repository.NewProjectRepository(db)
	fileRepo := repository.NewFileRepository(db)
	compRepo := repository.NewCompilationRepository(db)
	collabRepo := repository.NewCollaboratorRepository(db)
	commentRepo := repository.NewCommentRepository(db)
	shareLinkRepo := repository.NewShareLinkRepository(db)

	// 7. Initialize Auth Client
	authClient := pkgauth.NewAuthClient(cfg.Auth.ServiceURL)

	// 8. Initialize Access Service (central permission resolver)
	accessSvc := service.NewAccessService(projectRepo, collabRepo)

	// 9. Initialize Compilation Engine
	compEngine := compiler.NewCompileEngine(cfg.Compiler, redisCache, store, db, compRepo, fileRepo, projectRepo)
	compEngine.Start()

	// 10. Initialize Services
	fileService := service.NewFileService(fileRepo, projectRepo, store, accessSvc)
	projectService := service.NewProjectService(projectRepo, fileService, accessSvc)
	compileService := service.NewCompileService(projectRepo, compRepo, compEngine, redisCache, store, accessSvc)
	templateService := service.NewTemplateService(projectRepo, fileService, "./templates")
	collabService := service.NewCollaboratorService(collabRepo, projectRepo, accessSvc, authClient)
	commentService := service.NewCommentService(commentRepo, accessSvc)

	// Determine frontend URL for share link construction
	frontendURL := "https://bdc.hpcc.vn"
	if cfg.App.Env != "production" {
		frontendURL = "http://localhost:3000"
	}
	shareLinkService := service.NewShareLinkService(shareLinkRepo, collabRepo, accessSvc, frontendURL)

	// 11. Initialize Handlers
	projectHandler := handler.NewProjectHandler(projectService)
	fileHandler := handler.NewFileHandler(fileService)
	compileHandler := handler.NewCompileHandler(compileService)
	templateHandler := handler.NewTemplateHandler(templateService)
	collabHandler := handler.NewCollaboratorHandler(collabService)
	commentHandler := handler.NewCommentHandler(commentService)
	shareLinkHandler := handler.NewShareLinkHandler(shareLinkService)

	// 12. Setup Gin Router
	if cfg.App.Env == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.New()
	r.Use(gin.Recovery())

	// Logger middleware using our logger
	r.Use(func(c *gin.Context) {
		path := c.Request.URL.Path
		if path == "/api/v1/health" {
			c.Next()
			return
		}
		start := time.Now()
		c.Next()
		latency := time.Since(start)
		logger.Info(fmt.Sprintf("%s %s %d %s", c.Request.Method, path, c.Writer.Status(), latency))
	})

	// CORS
	r.Use(middleware.CORS([]string{
		"http://localhost:3000",
		"http://localhost:3001",
		"https://bdc.hpcc.vn",
		"http://frontend:3000",
		"http://frontend:3001",
	}))

	// Health check handler
	healthHandler := func(c *gin.Context) {
		dbErr := db.PingContext(c.Request.Context())
		redisClient := redisCache.GetClient()
		redisErr := redisClient.Ping(c.Request.Context()).Err()

		status := "healthy"
		if dbErr != nil || redisErr != nil {
			status = "unhealthy"
		}

		c.JSON(http.StatusOK, gin.H{
			"status": status,
			"database": func() string {
				if dbErr != nil {
					return "down: " + dbErr.Error()
				}
				return "up"
			}(),
			"redis": func() string {
				if redisErr != nil {
					return "down: " + redisErr.Error()
				}
				return "up"
			}(),
			"queue_depth": compEngine.GetQueueDepth(),
		})
	}

	r.GET("/api/v1/health", healthHandler)
	r.HEAD("/api/v1/health", healthHandler)

	// API Group with JWT Auth
	api := r.Group("/api/v1")
	api.Use(middleware.AuthMiddleware(cfg.JWT.Secret))
	{
		// Projects
		api.POST("/projects", projectHandler.Create)
		api.GET("/projects", projectHandler.List)
		api.GET("/projects/:id", projectHandler.Get)
		api.PUT("/projects/:id", projectHandler.Update)
		api.DELETE("/projects/:id", projectHandler.Delete)

		// Files
		api.POST("/projects/:id/files", fileHandler.Upload)
		api.POST("/projects/:id/files/upload-zip", fileHandler.UploadZip)
		api.POST("/projects/:id/files/create", fileHandler.Create)
		api.GET("/projects/:id/files", fileHandler.List)
		api.GET("/projects/:id/files/:fileId", fileHandler.GetContent)
		api.PUT("/projects/:id/files/:fileId", fileHandler.UpdateContent)
		api.PUT("/projects/:id/files/:fileId/rename", fileHandler.Rename)
		api.DELETE("/projects/:id/files/:fileId", fileHandler.Delete)

		// Compilation (Rate limited to 5 compiles per minute)
		api.POST("/projects/:id/compile", middleware.RateLimitByUser(redisCache, "compile", 5, 1*time.Minute), compileHandler.Compile)
		api.GET("/compile/jobs/:jobId/status", compileHandler.GetStatus)
		api.GET("/compile/jobs/:jobId/pdf", compileHandler.StreamPdf)
		api.GET("/compile/jobs/:jobId/log", compileHandler.GetLog)

		// Templates & Packages
		api.GET("/templates", templateHandler.ListTemplates)
		api.GET("/templates/:id", templateHandler.GetTemplate)
		api.POST("/projects/from-template/:id", templateHandler.CreateFromTemplate)
		api.GET("/packages", templateHandler.ListPackages)

		// Collaborators
		api.POST("/projects/:id/collaborators", collabHandler.Add)
		api.GET("/projects/:id/collaborators", collabHandler.List)
		api.PUT("/projects/:id/collaborators/:userId", collabHandler.UpdateRole)
		api.DELETE("/projects/:id/collaborators/:userId", collabHandler.Remove)

		// Comments
		api.POST("/projects/:id/comments", commentHandler.Create)
		api.GET("/projects/:id/comments", commentHandler.ListByProject)
		api.GET("/projects/:id/files/:fileId/comments", commentHandler.ListByFile)
		api.PUT("/projects/:id/comments/:commentId", commentHandler.Update)
		api.DELETE("/projects/:id/comments/:commentId", commentHandler.Delete)
		api.POST("/projects/:id/comments/:commentId/resolve", commentHandler.Resolve)
		api.POST("/projects/:id/comments/:commentId/unresolve", commentHandler.Unresolve)

		// Share Links
		api.POST("/projects/:id/share-links", shareLinkHandler.Create)
		api.GET("/projects/:id/share-links", shareLinkHandler.List)
		api.DELETE("/projects/:id/share-links/:linkId", shareLinkHandler.Deactivate)

		// Join via share link (token only, no project ID needed)
		api.POST("/share/join/:token", shareLinkHandler.Join)
	}

	// 13. Start HTTP Server
	srv := &http.Server{
		Addr:         ":" + cfg.App.Port,
		Handler:      r,
		ReadTimeout:  cfg.Server.ReadTimeout,
		WriteTimeout: cfg.Server.WriteTimeout,
		IdleTimeout:  cfg.Server.IdleTimeout,
	}

	go func() {
		logger.Info(fmt.Sprintf("HTTP Server listening on port %s", cfg.App.Port))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("Failed to start server", err)
		}
	}()

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	logger.Info("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		logger.Fatal("Server forced to shutdown", err)
	}

	logger.Info("LaTeX Service exited gracefully")
}
