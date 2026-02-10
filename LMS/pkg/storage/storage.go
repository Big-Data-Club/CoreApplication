// pkg/storage/storage.go
package storage

import (
	"context"
)

// Storage defines the interface for file storage
type Storage interface {
	Upload(ctx context.Context, filename string, data []byte) (string, error)
	Download(ctx context.Context, filename string) ([]byte, error)
	Delete(ctx context.Context, filename string) error
}