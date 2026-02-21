// pkg/storage/local.go
package storage

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// LocalStorage implements Storage interface for local filesystem
type LocalStorage struct {
	basePath string
}

var _ Storage = (*LocalStorage)(nil)

// NewLocalStorage creates a new local storage
func NewLocalStorage(basePath string) (*LocalStorage, error) {
	if err := os.MkdirAll(basePath, 0755); err != nil {
		return nil, fmt.Errorf("failed to create storage directory: %w", err)
	}

	return &LocalStorage{basePath: basePath}, nil
}

func (s *LocalStorage) Upload(ctx context.Context, filename string, reader io.Reader, size int64, contentType string) (string, error) {
	filePath := filepath.Join(s.basePath, filename)

	if err := os.MkdirAll(filepath.Dir(filePath), 0755); err != nil {
		return "", fmt.Errorf("failed to create directory: %w", err)
	}

	dst, err := os.OpenFile(filePath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	if err != nil {
		return "", fmt.Errorf("failed to create file: %w", err)
	}
	defer dst.Close()

	if _, err := io.Copy(dst, reader); err != nil {
		os.Remove(filePath)
		return "", fmt.Errorf("failed to write file: %w", err)
	}

	return filePath, nil
}

func (s *LocalStorage) GetObject(ctx context.Context, filename string) (*ObjectResult, error) {
	filePath := filepath.Join(s.basePath, filename)

	f, err := os.Open(filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("file not found: %s", filename)
		}
		return nil, fmt.Errorf("failed to open file: %w", err)
	}

	info, err := f.Stat()
	if err != nil {
		f.Close()
		return nil, fmt.Errorf("failed to stat file: %w", err)
	}

	return &ObjectResult{
		Body:         f,
		Size:         info.Size(),
		ContentType:  "",
		LastModified: info.ModTime(),
		ETag:         fmt.Sprintf(`"%x-%x"`, info.ModTime().Unix(), info.Size()),
	}, nil
}

func (s *LocalStorage) Delete(ctx context.Context, filename string) error {
	filePath := filepath.Join(s.basePath, filename)

	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		return fmt.Errorf("file not found: %s", filename)
	}

	if err := os.Remove(filePath); err != nil {
		return fmt.Errorf("failed to delete file: %w", err)
	}

	return nil
}