// Package storage provides private, S3-compatible attachment storage for chat.
package storage

import (
	"context"
	"fmt"
	"io"
	"time"

	"chat-service/internal/config"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type ObjectStore struct {
	client *minio.Client
	bucket string
}

type Object struct {
	Body        io.ReadSeekCloser
	Size        int64
	ContentType string
	ModifiedAt  time.Time
}

// NewObjectStore validates connectivity once at startup. Callers may choose to
// keep chat online without attachments if this dependency is unavailable.
func NewObjectStore(cfg config.StorageConfig) (*ObjectStore, error) {
	if cfg.Endpoint == "" || cfg.AccessKey == "" || cfg.SecretKey == "" || cfg.Bucket == "" {
		return nil, fmt.Errorf("chat attachment storage is not configured")
	}
	client, err := minio.New(cfg.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: cfg.UseSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("create object client: %w", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	if _, err := client.BucketExists(ctx, cfg.Bucket); err != nil {
		return nil, fmt.Errorf("check object bucket %q: %w", cfg.Bucket, err)
	}
	return &ObjectStore{client: client, bucket: cfg.Bucket}, nil
}

// Put streams the request to object storage; it never buffers an attachment in
// the chat pod. A known size is preferred, but multipart streaming is used for
// browser uploads where the part length is not supplied.
func (s *ObjectStore) Put(ctx context.Context, key string, body io.Reader, contentType string) (int64, error) {
	info, err := s.client.PutObject(ctx, s.bucket, key, body, -1, minio.PutObjectOptions{
		ContentType: contentType,
		PartSize:    5 * 1024 * 1024,
	})
	if err != nil {
		return 0, fmt.Errorf("put object: %w", err)
	}
	return info.Size, nil
}

func (s *ObjectStore) Get(ctx context.Context, key string) (*Object, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("open object: %w", err)
	}
	info, err := obj.Stat()
	if err != nil {
		_ = obj.Close()
		return nil, fmt.Errorf("stat object: %w", err)
	}
	return &Object{Body: obj, Size: info.Size, ContentType: info.ContentType, ModifiedAt: info.LastModified}, nil
}

func (s *ObjectStore) Delete(ctx context.Context, key string) error {
	return s.client.RemoveObject(ctx, s.bucket, key, minio.RemoveObjectOptions{})
}
