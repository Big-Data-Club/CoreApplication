package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"chat-service/internal/config"
	"chat-service/internal/handler"
	"chat-service/internal/middleware"
	"chat-service/pkg/cache"
	"chat-service/pkg/database"
	"chat-service/pkg/hub"
	"chat-service/pkg/logger"
	"chat-service/internal/repository"

	"github.com/gin-gonic/gin"
)

func main() {
	// ── 1. Configuration ──────────────────────────────────────────────────────
	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "config: %v\n", err)
		os.Exit(1)
	}

	logger.SetLevel(cfg.App.LogLevel)
	logger.Infof("Starting %s (env=%s, port=%s)", cfg.App.Name, cfg.App.Env, cfg.App.Port)

	// Use all available CPU cores for goroutine scheduling
	runtime.GOMAXPROCS(runtime.NumCPU())

	// ── 2. Database ───────────────────────────────────────────────────────────
	db, err := database.NewPostgresDB(cfg.Database)
	if err != nil {
		logger.Errorf("database init: %v", err)
		os.Exit(1)
	}
	defer db.Close()

	if err := database.RunMigrations(db, "./migrations"); err != nil {
		logger.Errorf("migrations: %v", err)
		os.Exit(1)
	}


	// ── 3. Redis ──────────────────────────────────────────────────────────────
	rdb, err := cache.NewRedisClient(cfg.Redis)
	if err != nil {
		logger.Errorf("redis init: %v", err)
		os.Exit(1)
	}
	defer rdb.Close()

	// ── 4. WebSocket Hub (Redis Pub/Sub backed) ───────────────────────────────
	wsHub := hub.New(rdb)
	go wsHub.Run()

	// ── 5. Repositories ───────────────────────────────────────────────────────
	userRepo := repository.NewUserRepository(db)
	chatRepo := repository.NewChatRepository(db)

	// Seed default "general" channel if none exist
	if seeded, err := chatRepo.SeedDefaultChannel(context.Background()); err != nil {
		logger.Warnf("seed default channel: %v", err)
	} else if seeded {
		logger.Info("Seeded default 'general' channel on startup")
	}

	// ── 6. Handlers ───────────────────────────────────────────────────────────
	syncHandler  := handler.NewSyncHandler(userRepo, chatRepo)
	chatHandler  := handler.NewChatHandler(chatRepo, userRepo, wsHub, cfg.JWT.Secret)
	adminHandler := handler.NewAdminHandler(chatRepo, userRepo)

	// ── 7. Router ─────────────────────────────────────────────────────────────
	if cfg.App.Env == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.Logger())
	r.Use(middleware.CORS(cfg.CORS.AllowedOrigins))

	// Health check — no auth
	healthHandler := func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":  "ok",
			"service": cfg.App.Name,
			"time":    time.Now().UTC(),
		})
	}
	r.GET("/health", healthHandler)
	r.HEAD("/health", healthHandler)

	// ── Sync routes (auth-service -> chat-service, secret-protected) ──────────
	sync := r.Group("/api/v1/sync", middleware.SyncSecret(cfg.Sync.Secret))
	{
		sync.POST("/user", syncHandler.SyncUser)
		sync.POST("/users/bulk", syncHandler.BulkSyncUsers)
		sync.DELETE("/user/:userId", syncHandler.DeleteUser)
	}

	// ── WebSocket (JWT via ?token= query param) ───────────────────────────────
	// Note: no Auth() middleware here — auth is done inside ServeWS
	r.GET("/api/v1/chat/ws", chatHandler.ServeWS)

	// ── Chat REST (JWT auth required) ─────────────────────────────────────────
	auth := r.Group("/api/v1", middleware.Auth(cfg.JWT.Secret))
	{
		chat := auth.Group("/chat")
		{
			chat.GET("/channels", chatHandler.ListChannels)
			chat.GET("/channels/:id/messages", chatHandler.ListMessages)
			chat.POST("/channels/:id/messages", chatHandler.SendMessage)
			chat.DELETE("/channels/:id/messages/:msgId", chatHandler.DeleteMessage)
			chat.GET("/users/search", chatHandler.SearchUsers)
			chat.POST("/dm", chatHandler.GetOrCreateDM)
		}

		// ── Admin routes (JWT + ADMIN role) ──────────────────────────────────
		admin := auth.Group("/admin", middleware.RequireAdmin())
		{
			adminChannels := admin.Group("/channels")
			{
				adminChannels.GET("", adminHandler.ListAllChannels)
				adminChannels.POST("", adminHandler.CreateChannel)
				adminChannels.PUT("/:id", adminHandler.UpdateChannel)
				adminChannels.DELETE("/:id", adminHandler.DeleteChannel)
				adminChannels.GET("/:id/roles", adminHandler.GetChannelRoles)
				adminChannels.PUT("/:id/roles", adminHandler.SetChannelRoles)
				adminChannels.GET("/:id/users", adminHandler.GetChannelUsers)
				adminChannels.PUT("/:id/users", adminHandler.SetChannelUsers)
			}
		}
	}

	// ── 8. HTTP Server with graceful shutdown ─────────────────────────────────
	srv := &http.Server{
		Addr:    ":" + cfg.App.Port,
		Handler: r,
		// No WriteTimeout — WebSocket connections are long-lived
		ReadTimeout:  cfg.Server.ReadTimeout,
		IdleTimeout:  cfg.Server.IdleTimeout,
	}

	// Start server in background goroutine
	serverErr := make(chan error, 1)
	go func() {
		logger.Infof("Listening on :%s", cfg.App.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	// ── 9. Graceful shutdown ──────────────────────────────────────────────────
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		logger.Infof("Received signal: %s — shutting down", sig)
	case err := <-serverErr:
		logger.Errorf("Server error: %v", err)
	}

	// Give in-flight requests time to complete
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), cfg.Server.ShutdownTimeout)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Errorf("Graceful shutdown failed: %v", err)
	}

	// Shutdown WebSocket hub (closes all client connections)
	wsHub.Shutdown()

	logger.Info("Chat service stopped cleanly")
}


