package compiler

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"latex-service/internal/config"
	"latex-service/internal/repository"
	"latex-service/pkg/cache"
	"latex-service/pkg/logger"
	"latex-service/pkg/storage"
)

type CompileJob struct {
	ID        string `json:"job_id"`
	ProjectID int64  `json:"project_id"`
	UserID    int64  `json:"user_id"`
	Compiler  string `json:"compiler"`
	MainFile  string `json:"main_file"`
}

type CompileEngine struct {
	workerCount int
	jobQueue    chan *CompileJob
	redis       *cache.RedisCache
	storage     storage.Storage
	db          *sql.DB
	compRepo    *repository.CompilationRepository
	fileRepo    *repository.FileRepository
	projectRepo *repository.ProjectRepository
	maxTimeout  time.Duration
	maxMemoryMB int
	tempDir     string
}

func NewCompileEngine(
	cfg config.CompilerConfig,
	redis *cache.RedisCache,
	storage storage.Storage,
	db *sql.DB,
	compRepo *repository.CompilationRepository,
	fileRepo *repository.FileRepository,
	projectRepo *repository.ProjectRepository,
) *CompileEngine {
	// Create temp directory if it doesn't exist
	if err := os.MkdirAll(cfg.TempDir, 0755); err != nil {
		logger.Error("Failed to create build temp dir", err)
	}

	return &CompileEngine{
		workerCount: cfg.WorkerCount,
		jobQueue:    make(chan *CompileJob, 500), // Queue capacity of 500
		redis:       redis,
		storage:     storage,
		db:          db,
		compRepo:    compRepo,
		fileRepo:    fileRepo,
		projectRepo: projectRepo,
		maxTimeout:  time.Duration(cfg.MaxTimeout) * time.Second,
		maxMemoryMB: cfg.MaxMemoryMB,
		tempDir:     cfg.TempDir,
	}
}

// Start spawns the worker pool
func (e *CompileEngine) Start() {
	logger.Info(fmt.Sprintf("Starting LaTeX compile engine with %d workers", e.workerCount))
	for i := 1; i <= e.workerCount; i++ {
		go e.worker(i)
	}
}

// Submit pushes a job to the queue, returning false if the queue is full
func (e *CompileEngine) Submit(job *CompileJob) bool {
	select {
	case e.jobQueue <- job:
		return true
	default:
		return false
	}
}

// GetQueueDepth returns the current number of pending jobs in the queue
func (e *CompileEngine) GetQueueDepth() int {
	return len(e.jobQueue)
}

func (e *CompileEngine) worker(workerID int) {
	logger.Info(fmt.Sprintf("Compile worker %d started", workerID))

	for job := range e.jobQueue {
		e.processJob(workerID, job)
	}
}

func (e *CompileEngine) processJob(workerID int, job *CompileJob) {
	ctx := context.Background()
	logger.Info(fmt.Sprintf("Worker %d processing job %s for project %d", workerID, job.ID, job.ProjectID))

	// Update job status in DB & Redis
	_ = e.updateJobStatus(ctx, job.ID, "compiling", nil, nil, nil, 0)

	// Create temp workspace
	buildDir := filepath.Join(e.tempDir, job.ID)
	outputDir := filepath.Join(buildDir, "output")

	defer func() {
		// Clean up build directory
		if err := os.RemoveAll(buildDir); err != nil {
			logger.Error(fmt.Sprintf("Failed to clean build dir %s", buildDir), err)
		}
	}()

	if err := os.MkdirAll(outputDir, 0755); err != nil {
		errMsg := fmt.Sprintf("failed to create build workspace: %v", err)
		_ = e.updateJobStatus(ctx, job.ID, "failed", nil, nil, &errMsg, 0)
		return
	}

	// 1. Download all files from project
	files, err := e.fileRepo.ListByProject(ctx, job.ProjectID)
	if err != nil {
		errMsg := fmt.Sprintf("failed to fetch project files metadata: %v", err)
		_ = e.updateJobStatus(ctx, job.ID, "failed", nil, nil, &errMsg, 0)
		return
	}

	for _, fileMeta := range files {
		localPath := filepath.Join(buildDir, fileMeta.Filename)

		// Create parent directories if any (e.g. image subdirectories)
		if err := os.MkdirAll(filepath.Dir(localPath), 0755); err != nil {
			errMsg := fmt.Sprintf("failed to create directory structure for file %s: %v", fileMeta.Filename, err)
			_ = e.updateJobStatus(ctx, job.ID, "failed", nil, nil, &errMsg, 0)
			return
		}

		// Download content from MinIO
		obj, err := e.storage.GetObject(ctx, fileMeta.Filepath)
		if err != nil {
			errMsg := fmt.Sprintf("failed to download file %s: %v", fileMeta.Filename, err)
			_ = e.updateJobStatus(ctx, job.ID, "failed", nil, nil, &errMsg, 0)
			return
		}

		localFile, err := os.Create(localPath)
		if err != nil {
			obj.Body.Close()
			errMsg := fmt.Sprintf("failed to write local file %s: %v", fileMeta.Filename, err)
			_ = e.updateJobStatus(ctx, job.ID, "failed", nil, nil, &errMsg, 0)
			return
		}

		_, err = io.Copy(localFile, obj.Body)
		localFile.Close()
		obj.Body.Close()

		if err != nil {
			errMsg := fmt.Sprintf("failed to save file %s: %v", fileMeta.Filename, err)
			_ = e.updateJobStatus(ctx, job.ID, "failed", nil, nil, &errMsg, 0)
			return
		}
	}

	// 2. Determine compiler path/command
	compilerCmd := job.Compiler
	if compilerCmd == "" {
		compilerCmd = "pdflatex"
	}

	// 3. Run compilation in sandbox
	res, err := RunCompiler(ctx, compilerCmd, buildDir, job.MainFile, e.maxTimeout)
	if err != nil {
		errMsg := fmt.Sprintf("sandbox execution error: %v", err)
		_ = e.updateJobStatus(ctx, job.ID, "failed", nil, &res.LogOutput, &errMsg, int(res.Duration.Milliseconds()))
		return
	}

	durationMs := int(res.Duration.Milliseconds())

	// Read compiler log output from file (more complete than combined output stdout)
	mainFileBase := filepath.Base(job.MainFile)
	mainFileExt := filepath.Ext(mainFileBase)
	mainFileName := mainFileBase[:len(mainFileBase)-len(mainFileExt)]
	logFilePath := filepath.Join(outputDir, mainFileName+".log")

	var logContent string
	if logBytes, logErr := os.ReadFile(logFilePath); logErr == nil {
		logContent = string(logBytes)
	} else {
		logContent = res.LogOutput // Fallback
	}

	if !res.Success {
		errMsg := res.ErrorMessage
		if errMsg == "" {
			errMsg = "Latex compilation failed. Check log for details."
		}
		_ = e.updateJobStatus(ctx, job.ID, "failed", nil, &logContent, &errMsg, durationMs)
		return
	}

	// Compile succeeded, locate PDF
	pdfFilePath := filepath.Join(outputDir, mainFileName+".pdf")
	pdfFile, err := os.Open(pdfFilePath)
	if err != nil {
		errMsg := fmt.Sprintf("PDF output not found: %v", err)
		_ = e.updateJobStatus(ctx, job.ID, "failed", &logContent, &logContent, &errMsg, durationMs)
		return
	}
	defer pdfFile.Close()

	pdfStat, err := pdfFile.Stat()
	if err != nil {
		errMsg := fmt.Sprintf("Failed to stat output PDF: %v", err)
		_ = e.updateJobStatus(ctx, job.ID, "failed", &logContent, &logContent, &errMsg, durationMs)
		return
	}

	// 4. Upload compiled PDF to MinIO
	pdfMinIOKey := fmt.Sprintf("compilations/%s.pdf", job.ID)
	_, err = e.storage.Upload(ctx, pdfMinIOKey, pdfFile, pdfStat.Size(), "application/pdf")
	if err != nil {
		errMsg := fmt.Sprintf("failed to save compiled PDF to storage: %v", err)
		_ = e.updateJobStatus(ctx, job.ID, "failed", &logContent, &logContent, &errMsg, durationMs)
		return
	}

	// 5. Update status to success
	_ = e.updateJobStatus(ctx, job.ID, "success", &pdfMinIOKey, &logContent, nil, durationMs)
	logger.Info(fmt.Sprintf("Compilation job %s completed successfully in %d ms", job.ID, durationMs))
}

func (e *CompileEngine) updateJobStatus(ctx context.Context, jobID string, status string, pdfPath *string, logOutput *string, errMsg *string, durationMs int) error {
	// 1. Update PostgreSQL
	if status != "compiling" {
		_ = e.compRepo.Update(ctx, jobID, status, pdfPath, logOutput, errMsg, durationMs)
	}

	// 2. Read latest status from DB to ensure consistency
	dbStatus, err := e.compRepo.GetByJobID(ctx, jobID)
	if err != nil {
		return err
	}

	// 3. Update Redis Cache (for polling)
	cacheKey := "latex_job:" + jobID
	statusJSON, _ := json.Marshal(dbStatus)
	_ = e.redis.Set(ctx, cacheKey, statusJSON, 24*time.Hour)

	return nil
}
