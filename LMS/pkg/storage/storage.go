// pkg/storage/storage.go
package storage

import (
	"context"
	"io"
	"time"
)

// Storage defines the interface for all file storage backends (MinIO, local, S3, etc.)
type Storage interface {
	Upload(ctx context.Context, filename string, reader io.Reader, size int64, contentType string) (string, error)
	GetObject(ctx context.Context, filename string) (*ObjectResult, error)
	Delete(ctx context.Context, filename string) error
}

type ObjectResult struct {
	Body         io.ReadSeekCloser
	Size         int64
	ContentType  string
	LastModified time.Time
	ETag         string
}