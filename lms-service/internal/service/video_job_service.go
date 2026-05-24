package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/kafka"
	"example/hello/pkg/logger"
)

var blacklistPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)ignore\s+previous\s+instructions`),
	regexp.MustCompile(`(?i)system\s*prompt`),
	regexp.MustCompile(`(?i)you\s+are\s+a`),
	regexp.MustCompile(`(?i)<script[^>]*>[\s\S]*?</script>`),
	regexp.MustCompile(`(?i)</?script[^>]*>`),
	regexp.MustCompile("(?i)```[\\s\\S]*```"),
}

type VideoJobService struct {
	videoJobRepo *repository.VideoJobRepository
	courseRepo   *repository.CourseRepository
	db           *sql.DB
}

func NewVideoJobService(
	videoJobRepo *repository.VideoJobRepository,
	courseRepo *repository.CourseRepository,
	db *sql.DB,
) *VideoJobService {
	return &VideoJobService{
		videoJobRepo: videoJobRepo,
		courseRepo:   courseRepo,
		db:           db,
	}
}

// CreateJob handles creation, validation, limits, sanitization, and queues the job.
func (s *VideoJobService) CreateJob(ctx context.Context, req dto.CreateVideoJobRequest, userID int64, role string) (*dto.VideoJobResponse, error) {
	// 1. Role validation
	if role != models.RoleAdmin && role != models.RoleTeacher {
		return nil, fmt.Errorf("permission denied: only teachers and admins can generate overview videos")
	}

	// 2. Ownership checking
	var courseID int64
	if req.TargetType == "course" {
		course, err := s.courseRepo.GetByID(ctx, req.TargetID)
		if err != nil {
			return nil, fmt.Errorf("failed to get course: %w", err)
		}
		if role != models.RoleAdmin && course.CreatedBy != userID {
			return nil, fmt.Errorf("permission denied: you do not own this course")
		}
		courseID = course.ID
	} else if req.TargetType == "section" {
		section, err := s.courseRepo.GetSectionByID(ctx, req.TargetID)
		if err != nil {
			return nil, fmt.Errorf("failed to get section: %w", err)
		}
		course, err := s.courseRepo.GetByID(ctx, section.CourseID)
		if err != nil {
			return nil, fmt.Errorf("failed to get course of section: %w", err)
		}
		if role != models.RoleAdmin && course.CreatedBy != userID {
			return nil, fmt.Errorf("permission denied: you do not own the course of this section")
		}
		courseID = course.ID
	} else {
		return nil, fmt.Errorf("invalid target type: %s", req.TargetType)
	}

	// 3. Rate limiting checks
	maxConcurrent := 2
	if limitEnv := os.Getenv("VIDEO_MAX_CONCURRENT_JOBS"); limitEnv != "" {
		if val, err := strconv.Atoi(limitEnv); err == nil {
			maxConcurrent = val
		}
	}

	maxDaily := 5
	if limitEnv := os.Getenv("VIDEO_MAX_DAILY_JOBS"); limitEnv != "" {
		if val, err := strconv.Atoi(limitEnv); err == nil {
			maxDaily = val
		}
	}

	activeCount, err := s.videoJobRepo.CountActiveJobs(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to count active jobs: %w", err)
	}
	if activeCount >= maxConcurrent {
		return nil, fmt.Errorf("rate limit exceeded: you currently have %d active jobs running (max concurrent limit: %d)", activeCount, maxConcurrent)
	}

	dailyCount, err := s.videoJobRepo.CountDailyJobs(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to count daily jobs: %w", err)
	}
	if dailyCount >= maxDaily {
		return nil, fmt.Errorf("rate limit exceeded: you have generated %d jobs in the last 24 hours (daily limit: %d)", dailyCount, maxDaily)
	}

	// 4. Sanitize prompt
	sanitizedPrompt := s.sanitizePrompt(req.CustomPrompt)

	// 5. Default templates and language
	lang := "vi"
	if req.Language != "" {
		lang = req.Language
	}

	template := "dark"
	if req.TemplateType != "" {
		template = req.TemplateType
	}

	job := &models.VideoGenerationJob{
		TargetType:   req.TargetType,
		TargetID:     req.TargetID,
		CustomPrompt: sql.NullString{String: sanitizedPrompt, Valid: sanitizedPrompt != ""},
		Language:     lang,
		TemplateType: template,
		CreatedBy:    userID,
		Status:       models.VideoJobStatusPending,
		Progress:     0,
		RetryCount:   0,
		MaxRetries:   3,
		Visibility:   models.VideoVisibilityUnlisted,
	}

	// Save to DB
	job, err = s.videoJobRepo.Create(ctx, job)
	if err != nil {
		return nil, fmt.Errorf("failed to create video job: %w", err)
	}

	// 6. Publish command to Kafka
	// Format Job ID with prefix "vid_"
	jobIDWithPrefix := "vid_" + job.ID

	var contentIDs []int64
	if job.TargetType == "section" {
		rows, err := s.db.QueryContext(ctx, "SELECT id FROM section_content WHERE section_id = $1", job.TargetID)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var cid int64
				if err := rows.Scan(&cid); err == nil {
					contentIDs = append(contentIDs, cid)
				}
			}
		} else {
			logger.Error("Failed to fetch section contents for video generation", err)
		}
	}

	payload := map[string]interface{}{
		"target_type":   job.TargetType,
		"target_id":     job.TargetID,
		"custom_prompt": sanitizedPrompt,
		"language":      job.Language,
		"template_type": job.TemplateType,
		"created_by":    job.CreatedBy,
		"content_ids":   contentIDs,
	}
	payloadBytes, _ := json.Marshal(payload)

	event := kafka.AICommandEvent{
		JobID:       jobIDWithPrefix,
		CommandType: "GENERATE_VIDEO",
		CourseID:    courseID,
		Payload:     json.RawMessage(payloadBytes),
		CreatedAt:   time.Now(),
	}

	err = kafka.PublishEvent(ctx, "lms.ai.command", []byte(job.ID), event)
	if err != nil {
		// Attempt to update status to FAILED
		_ = s.videoJobRepo.UpdateError(ctx, job.ID, "Failed to publish Kafka command: "+err.Error(), 0)
		return nil, fmt.Errorf("failed to queue video generation command: %w", err)
	}

	return s.mapToDTO(job), nil
}

// GetJob retrieves a job and checks ownership.
func (s *VideoJobService) GetJob(ctx context.Context, jobID string, userID int64, role string) (*dto.VideoJobResponse, error) {
	job, err := s.videoJobRepo.GetByID(ctx, jobID)
	if err != nil {
		return nil, fmt.Errorf("failed to get job: %w", err)
	}

	if role != models.RoleAdmin && job.CreatedBy != userID {
		return nil, fmt.Errorf("permission denied: you do not own this job")
	}

	return s.mapToDTO(job), nil
}

// ListJobs lists jobs for a specific target.
func (s *VideoJobService) ListJobs(ctx context.Context, targetType string, targetID int64, userID int64, role string) (*dto.VideoJobListResponse, error) {
	jobs, err := s.videoJobRepo.ListByTarget(ctx, targetType, targetID)
	if err != nil {
		return nil, fmt.Errorf("failed to list jobs: %w", err)
	}

	// Filter or mapping
	var dtos []dto.VideoJobResponse
	for _, j := range jobs {
		// Teachers/Admins can see jobs. If Teacher, check course ownership
		if role != models.RoleAdmin && j.CreatedBy != userID {
			continue // Only allow viewing owned jobs or if admin
		}
		dtos = append(dtos, *s.mapToDTO(j))
	}

	return &dto.VideoJobListResponse{
		Jobs:       dtos,
		TotalCount: len(dtos),
	}, nil
}

// PublishVideo changes visibility from unlisted to public on YouTube.
func (s *VideoJobService) PublishVideo(ctx context.Context, jobID string, userID int64, role string) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	job, err := s.videoJobRepo.LockAndGetForPublish(ctx, tx, jobID)
	if err != nil {
		return fmt.Errorf("failed to lock and get job: %w", err)
	}

	if role != models.RoleAdmin && job.CreatedBy != userID {
		return fmt.Errorf("permission denied: you do not own this job")
	}

	if job.Status != models.VideoJobStatusCompleted {
		return fmt.Errorf("cannot publish video: job is in status %s (must be COMPLETED)", job.Status)
	}

	if job.Visibility == models.VideoVisibilityPublic {
		return fmt.Errorf("video is already public")
	}

	if !job.YoutubeVideoID.Valid || job.YoutubeVideoID.String == "" {
		return fmt.Errorf("cannot publish video: YouTube Video ID is missing")
	}

	// Set status to PUBLISHING in database
	err = s.videoJobRepo.SetPublishing(ctx, tx, job.ID)
	if err != nil {
		return fmt.Errorf("failed to set status to publishing: %w", err)
	}

	// Commit transaction to release lock before Kafka blocking call
	err = tx.Commit()
	if err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	// Publish command to Kafka to tell worker to change video to public
	jobIDWithPrefix := "vid_" + job.ID
	payload := map[string]interface{}{
		"youtube_video_id": job.YoutubeVideoID.String,
	}
	payloadBytes, _ := json.Marshal(payload)

	event := kafka.AICommandEvent{
		JobID:       jobIDWithPrefix,
		CommandType: "PUBLISH_VIDEO",
		Payload:     json.RawMessage(payloadBytes),
		CreatedAt:   time.Now(),
	}

	err = kafka.PublishEvent(ctx, "lms.ai.command", []byte(job.ID), event)
	if err != nil {
		// Roll back database state to completed
		_ = s.videoJobRepo.UpdateStatus(ctx, job.ID, models.VideoJobStatusCompleted, 100)
		return fmt.Errorf("failed to publish publish_video command: %w", err)
	}

	return nil
}

// IsVideoJob determines if a job ID corresponds to a video generation job.
func (s *VideoJobService) IsVideoJob(ctx context.Context, jobID string) (bool, error) {
	// Strip prefix if present
	cleanID := strings.TrimPrefix(jobID, "vid_")
	
	// If cleanID is still a valid UUID, try querying the database
	uuidRegex := regexp.MustCompile(`^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$`)
	if !uuidRegex.MatchString(cleanID) {
		return false, nil
	}

	if s.videoJobRepo == nil {
		return false, fmt.Errorf("repository is not initialized")
	}

	_, err := s.videoJobRepo.GetByID(ctx, cleanID)
	if err != nil {
		if err == sql.ErrNoRows {
			return false, nil
		}
		return false, err
	}
	return true, nil
}


// HandleStatusUpdate handles incoming Kafka status events.
func (s *VideoJobService) HandleStatusUpdate(ctx context.Context, event kafka.AIJobStatusEvent) error {
	cleanID := strings.TrimPrefix(event.JobID, "vid_")
	logger.Info(fmt.Sprintf("Handling video job status update: jobID=%s, cleanID=%s, status=%s, progress=%d", event.JobID, cleanID, event.Status, event.Progress))

	// Get current job state
	job, err := s.videoJobRepo.GetByID(ctx, cleanID)
	if err != nil {
		return fmt.Errorf("job not found: %s: %w", cleanID, err)
	}

	if event.Status == "failed" {
		retryCount := job.RetryCount
		logger.Error(fmt.Sprintf("Video job %s failed: %s", cleanID, event.Error), nil)
		return s.videoJobRepo.UpdateError(ctx, cleanID, event.Error, retryCount)
	}

	// Check if this is a completion event for GENERATE_VIDEO or PUBLISH_VIDEO
	if event.Status == "completed" {
		// Determine command completed by analyzing payload results or visibility
		// If there is YouTube details in result, it's GENERATE_VIDEO completion
		if event.Result != nil {
			resultBytes, err := json.Marshal(event.Result)
			if err == nil {
				var resMap map[string]interface{}
				if json.Unmarshal(resultBytes, &resMap) == nil {
					// Check if result has visibility = "public" (PUBLISH_VIDEO completion)
					if visibility, ok := resMap["visibility"].(string); ok && visibility == "public" {
						return s.videoJobRepo.SetPublic(ctx, cleanID)
					}

					// Otherwise, it is GENERATE_VIDEO completion
					ytID, _ := resMap["youtube_video_id"].(string)
					ytURL, _ := resMap["youtube_url"].(string)
					if ytID != "" && ytURL != "" {
						err = s.videoJobRepo.UpdateYouTubeInfo(ctx, cleanID, ytID, ytURL)
						if err != nil {
							return fmt.Errorf("failed to save YouTube info: %w", err)
						}
					}
				}
			}
		}

		// Update overall job status to COMPLETED
		return s.videoJobRepo.UpdateStatus(ctx, cleanID, models.VideoJobStatusCompleted, 100)
	}

	// Handle processing/progress status updates
	if event.Status == "processing" {
		var statusStr string
		progress := event.Progress

		// Determine sub-status string based on progress ranges
		switch {
		case progress < 15:
			statusStr = models.VideoJobStatusPending
		case progress < 30:
			statusStr = models.VideoJobStatusPlanning
		case progress < 45:
			statusStr = models.VideoJobStatusScripting
		case progress < 80:
			statusStr = models.VideoJobStatusRendering
		default:
			statusStr = models.VideoJobStatusUploading
		}

		return s.videoJobRepo.UpdateStatus(ctx, cleanID, statusStr, progress)
	}

	return fmt.Errorf("unrecognized event status: %s", event.Status)
}

func (s *VideoJobService) sanitizePrompt(prompt string) string {
	if prompt == "" {
		return ""
	}

	// Remove html/script tags
	sanitized := prompt
	for _, pattern := range blacklistPatterns {
		sanitized = pattern.ReplaceAllString(sanitized, "")
	}

	return strings.TrimSpace(sanitized)
}

func (s *VideoJobService) mapToDTO(j *models.VideoGenerationJob) *dto.VideoJobResponse {
	var customPrompt string
	if j.CustomPrompt.Valid {
		customPrompt = j.CustomPrompt.String
	}

	var errorMsg string
	if j.LastErrorMessage.Valid {
		errorMsg = j.LastErrorMessage.String
	}

	var ytID string
	if j.YoutubeVideoID.Valid {
		ytID = j.YoutubeVideoID.String
	}

	var ytURL string
	if j.YoutubeURL.Valid {
		ytURL = j.YoutubeURL.String
	}

	return &dto.VideoJobResponse{
		ID:               j.ID,
		TargetType:       j.TargetType,
		TargetID:         j.TargetID,
		CustomPrompt:     customPrompt,
		Language:         j.Language,
		TemplateType:     j.TemplateType,
		CreatedBy:        j.CreatedBy,
		Status:           j.Status,
		Progress:         j.Progress,
		RetryCount:       j.RetryCount,
		LastErrorMessage: errorMsg,
		YoutubeVideoID:   ytID,
		YoutubeURL:       ytURL,
		Visibility:       j.Visibility,
		CreatedAt:        j.CreatedAt,
		UpdatedAt:        j.UpdatedAt,
	}
}
