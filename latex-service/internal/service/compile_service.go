package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"time"

	"latex-service/internal/compiler"
	"latex-service/internal/dto"
	"latex-service/internal/repository"
	"latex-service/pkg/cache"
	"latex-service/pkg/storage"

	"github.com/google/uuid"
)

type CompileService struct {
	projectRepo *repository.ProjectRepository
	compRepo    *repository.CompilationRepository
	engine      *compiler.CompileEngine
	redis       *cache.RedisCache
	storage     storage.Storage
	accessSvc   *AccessService
}

func NewCompileService(
	projectRepo *repository.ProjectRepository,
	compRepo *repository.CompilationRepository,
	engine *compiler.CompileEngine,
	redis *cache.RedisCache,
	storage storage.Storage,
	accessSvc *AccessService,
) *CompileService {
	return &CompileService{
		projectRepo: projectRepo,
		compRepo:    compRepo,
		engine:      engine,
		redis:       redis,
		storage:     storage,
		accessSvc:   accessSvc,
	}
}

// Compile submits a new compilation job
func (s *CompileService) Compile(ctx context.Context, userID int64, projectID int64, req *dto.CompileRequest) (*dto.CompileResponse, error) {
	// 1. Verify project exists and user has at least editor access
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return nil, err
	}

	p, err := s.projectRepo.GetByIDRaw(ctx, projectID)
	if err != nil {
		return nil, fmt.Errorf("failed to verify project: %w", err)
	}

	// 2. Determine compiler
	compilerCmd := p.Compiler
	if req.Compiler != "" {
		compilerCmd = req.Compiler
	}

	// 3. Generate job ID
	jobID := uuid.New().String()

	// 4. Create database record
	comp, err := s.compRepo.Create(ctx, projectID, userID, jobID, compilerCmd)
	if err != nil {
		return nil, fmt.Errorf("failed to create compilation record: %w", err)
	}

	// 5. Submit to compiler engine
	job := &compiler.CompileJob{
		ID:        jobID,
		ProjectID: projectID,
		UserID:    userID,
		Compiler:  compilerCmd,
		MainFile:  p.MainFile,
	}

	// Queue job
	success := s.engine.Submit(job)
	if !success {
		// Queue overflow
		errMsg := "Compilation server is currently busy. Queue is full."
		_ = s.compRepo.Update(ctx, jobID, "failed", nil, nil, &errMsg, 0)
		return nil, errors.New("compilation queue is full, please try again later")
	}

	// Write initial status to Redis for instant polling availability
	// Status is queued
	// We can reuse the updateJobStatus-like behavior
	cacheKey := "latex_job:" + jobID
	// Serialize comp status
	// Wait, we can serialize the CompileStatusResponse struct
	statusJSON, _ := jsonMarshal(comp) // Wait! Let's write standard json.Marshal
	_ = s.redis.Set(ctx, cacheKey, statusJSON, 24*time.Hour)

	return &dto.CompileResponse{
		JobID:     jobID,
		ProjectID: projectID,
		Status:    "queued",
	}, nil
}

// GetStatus retrieves the compilation job status (checks Redis first, falls back to DB)
func (s *CompileService) GetStatus(ctx context.Context, userID int64, jobID string) (*dto.CompileStatusResponse, error) {
	cacheKey := "latex_job:" + jobID
	val, err := s.redis.Get(ctx, cacheKey)
	if err == nil && val != "" {
		var resp dto.CompileStatusResponse
		if jsonErr := jsonUnmarshal(val, &resp); jsonErr == nil {
			// Verify ownership
			if resp.UserID != userID {
				return nil, errors.New("unauthorized to view compile status")
			}
			return &resp, nil
		}
	}

	// Fallback to DB
	resp, err := s.compRepo.GetByJobID(ctx, jobID)
	if err != nil {
		return nil, err
	}

	if resp.UserID != userID {
		return nil, errors.New("unauthorized to view compile status")
	}

	return resp, nil
}

// StreamPdf streams the compiled PDF from storage
func (s *CompileService) StreamPdf(ctx context.Context, userID int64, jobID string) (io.ReadCloser, int64, error) {
	// Verify job ownership and status
	status, err := s.GetStatus(ctx, userID, jobID)
	if err != nil {
		return nil, 0, err
	}

	if status.Status != "success" || status.PdfPath == nil {
		return nil, 0, errors.New("PDF is not available because compilation status is: " + status.Status)
	}

	obj, err := s.storage.GetObject(ctx, *status.PdfPath)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to retrieve PDF from storage: %w", err)
	}

	return obj.Body, obj.Size, nil
}

// Helper JSON Marshal/Unmarshal
func jsonMarshal(v interface{}) (string, error) {
	bytes, err := json.Marshal(v)
	return string(bytes), err
}

func jsonUnmarshal(data string, v interface{}) error {
	return json.Unmarshal([]byte(data), v)
}

