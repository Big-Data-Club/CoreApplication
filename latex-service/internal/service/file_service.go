package service

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"mime"
	"path/filepath"
	"strings"

	"latex-service/internal/dto"
	"latex-service/internal/repository"
	"latex-service/pkg/storage"
)

type FileService struct {
	fileRepo    *repository.FileRepository
	projectRepo *repository.ProjectRepository
	storage     storage.Storage
	accessSvc   *AccessService
}

func NewFileService(fileRepo *repository.FileRepository, projectRepo *repository.ProjectRepository, store storage.Storage, accessSvc *AccessService) *FileService {
	return &FileService{
		fileRepo:    fileRepo,
		projectRepo: projectRepo,
		storage:     store,
		accessSvc:   accessSvc,
	}
}

// UploadFile uploads a single file to storage and creates database record
func (s *FileService) UploadFile(ctx context.Context, userID int64, projectID int64, filename string, reader io.Reader, size int64, contentType string) (*dto.FileResponse, error) {
	// Verify project access (editor or above)
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return nil, fmt.Errorf("failed to verify project access: %w", err)
	}

	// Read content to calculate SHA-256 hash and size if size is unknown or for safety
	// Wait, we don't want to buffer huge files in memory, but we need the hash.
	// For ordinary text and image files (usually < 10MB), buffering is okay.
	// Let's copy to a buffer to hash it.
	buf := new(bytes.Buffer)
	teeReader := io.TeeReader(reader, buf)

	hasher := sha256.New()
	writtenSize, err := io.Copy(hasher, teeReader)
	if err != nil {
		return nil, fmt.Errorf("failed to process file content: %w", err)
	}

	if size <= 0 {
		size = writtenSize
	}

	hashStr := hex.EncodeToString(hasher.Sum(nil))

	// MinIO object key format: projects/{project_id}/{filename}
	objectKey := fmt.Sprintf("projects/%d/%s", projectID, filename)

	if contentType == "" {
		contentType = mime.TypeByExtension(filepath.Ext(filename))
		if contentType == "" {
			contentType = "application/octet-stream"
		}
	}

	// Upload to MinIO
	_, err = s.storage.Upload(ctx, objectKey, buf, size, contentType)
	if err != nil {
		return nil, fmt.Errorf("failed to upload to storage: %w", err)
	}

	// Save to DB
	resp, err := s.fileRepo.Create(ctx, projectID, filename, objectKey, size, contentType, hashStr)
	if err != nil {
		return nil, fmt.Errorf("failed to save file metadata: %w", err)
	}

	return resp, nil
}

// GetFileContent retrieves file content as a string (primarily for .tex files)
func (s *FileService) GetFileContent(ctx context.Context, userID int64, projectID int64, fileID int64) (string, error) {
	// Verify project access (viewer or above)
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessViewer); err != nil {
		return "", fmt.Errorf("failed to verify project access: %w", err)
	}

	fileMeta, err := s.fileRepo.GetByID(ctx, fileID)
	if err != nil {
		return "", err
	}

	if fileMeta.ProjectID != projectID {
		return "", errors.New("file does not belong to project")
	}

	obj, err := s.storage.GetObject(ctx, fileMeta.Filepath)
	if err != nil {
		return "", fmt.Errorf("failed to get file from storage: %w", err)
	}
	defer obj.Body.Close()

	contentBytes, err := io.ReadAll(obj.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read file content: %w", err)
	}

	return string(contentBytes), nil
}

// UpdateFileContent updates the content of a text file
func (s *FileService) UpdateFileContent(ctx context.Context, userID int64, projectID int64, fileID int64, content string) error {
	// Verify project access (editor or above)
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return fmt.Errorf("failed to verify project access: %w", err)
	}

	fileMeta, err := s.fileRepo.GetByID(ctx, fileID)
	if err != nil {
		return err
	}

	if fileMeta.ProjectID != projectID {
		return errors.New("file does not belong to project")
	}

	// Compute new size and hash
	contentBytes := []byte(content)
	size := int64(len(contentBytes))
	hasher := sha256.New()
	hasher.Write(contentBytes)
	hashStr := hex.EncodeToString(hasher.Sum(nil))

	reader := bytes.NewReader(contentBytes)

	// Upload updated content to MinIO
	_, err = s.storage.Upload(ctx, fileMeta.Filepath, reader, size, fileMeta.MimeType)
	if err != nil {
		return fmt.Errorf("failed to upload content: %w", err)
	}

	// Update DB metadata
	err = s.fileRepo.UpdateMetadata(ctx, fileID, size, hashStr)
	if err != nil {
		return fmt.Errorf("failed to update metadata: %w", err)
	}

	return nil
}

// ListFiles lists all files in a project
func (s *FileService) ListFiles(ctx context.Context, userID int64, projectID int64) ([]*dto.FileResponse, error) {
	// Verify project access (viewer or above)
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessViewer); err != nil {
		return nil, fmt.Errorf("failed to verify project access: %w", err)
	}

	return s.fileRepo.ListByProject(ctx, projectID)
}

// DeleteFile deletes a file from project
func (s *FileService) DeleteFile(ctx context.Context, userID int64, projectID int64, fileID int64) error {
	// Verify project access (editor or above)
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return fmt.Errorf("failed to verify project access: %w", err)
	}

	fileMeta, err := s.fileRepo.GetByID(ctx, fileID)
	if err != nil {
		return err
	}

	if fileMeta.ProjectID != projectID {
		return errors.New("file does not belong to project")
	}

	// Delete from storage
	err = s.storage.Delete(ctx, fileMeta.Filepath)
	if err != nil {
		// Log error but proceed to delete from DB to prevent orphaned DB entries
		// Actually, we can log and proceed
	}

	// Delete from DB
	return s.fileRepo.Delete(ctx, fileID)
}

// ExtractAndUploadZip extracts a ZIP file and uploads all files to the project
func (s *FileService) ExtractAndUploadZip(ctx context.Context, userID int64, projectID int64, zipReader io.ReaderAt, size int64) ([]*dto.FileResponse, error) {
	// Verify project access (editor or above)
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return nil, fmt.Errorf("failed to verify project access: %w", err)
	}

	r, err := zip.NewReader(zipReader, size)
	if err != nil {
		return nil, fmt.Errorf("failed to open zip archive: %w", err)
	}

	var uploadedFiles []*dto.FileResponse

	for _, f := range r.File {
		// Skip directories
		if f.FileInfo().IsDir() {
			continue
		}

		// Prevent ZIP Slip vulnerability (path traversal)
		cleanName := filepath.Clean(f.Name)
		if strings.HasPrefix(cleanName, "..") || strings.HasPrefix(cleanName, "/") {
			continue
		}

		rc, err := f.Open()
		if err != nil {
			return nil, fmt.Errorf("failed to open zip file member %s: %w", f.Name, err)
		}

		// Upload the file member
		// Replace backslashes with forward slashes for cross-platform paths
		standardizedName := strings.ReplaceAll(f.Name, "\\", "/")
		resp, err := s.UploadFile(ctx, userID, projectID, standardizedName, rc, int64(f.UncompressedSize64), "")
		rc.Close()

		if err != nil {
			return nil, fmt.Errorf("failed to upload zip file member %s: %w", f.Name, err)
		}

		uploadedFiles = append(uploadedFiles, resp)
	}

	return uploadedFiles, nil
}

// RenameFile renames a file in the project
func (s *FileService) RenameFile(ctx context.Context, userID int64, projectID int64, fileID int64, newFilename string) error {
	// Verify project access (editor or above)
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return fmt.Errorf("failed to verify project access: %w", err)
	}

	fileMeta, err := s.fileRepo.GetByID(ctx, fileID)
	if err != nil {
		return err
	}

	if fileMeta.ProjectID != projectID {
		return errors.New("file does not belong to project")
	}

	// Normalize filename
	newFilename = strings.TrimSpace(newFilename)
	if newFilename == "" {
		return errors.New("filename cannot be empty")
	}

	// Update DB filename
	err = s.fileRepo.UpdateFilename(ctx, fileID, newFilename)
	if err != nil {
		return fmt.Errorf("failed to rename file: %w", err)
	}

	return nil
}

// CreateFile creates a new file with content
func (s *FileService) CreateFile(ctx context.Context, userID int64, projectID int64, filename string, content string) (*dto.FileResponse, error) {
	// Normalize filename
	filename = strings.TrimSpace(filename)
	if filename == "" {
		return nil, errors.New("filename cannot be empty")
	}

	buf := bytes.NewBufferString(content)
	return s.UploadFile(ctx, userID, projectID, filename, buf, int64(buf.Len()), "text/plain")
}
