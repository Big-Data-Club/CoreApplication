// pkg/storage/minio.go
package storage

import (
	"context"
	"fmt"
	"io"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"example/hello/internal/config"
)

// MinIOStorage implements Storage interface for MinIO / S3-compatible object storage
type MinIOStorage struct {
	client *minio.Client
	bucket string
}

// NewMinIOStorage creates a new MinIO storage and ensures bucket exists.
func NewMinIOStorage(cfg config.StorageConfig) (*MinIOStorage, error) {
	client, err := minio.New(cfg.MinIOEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIOAccessKey, cfg.MinIOSecretKey, ""),
		Secure: cfg.MinIOUseSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create MinIO client: %w", err)
	}

	// Dùng timeout để không hang nếu MinIO không available lúc khởi động
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	exists, err := client.BucketExists(ctx, cfg.MinIOBucket)
	if err != nil {
		return nil, fmt.Errorf("failed to check bucket existence: %w", err)
	}

	if !exists {
		mkCtx, mkCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer mkCancel()
		if err = client.MakeBucket(mkCtx, cfg.MinIOBucket, minio.MakeBucketOptions{}); err != nil {
			return nil, fmt.Errorf("failed to create bucket %q: %w", cfg.MinIOBucket, err)
		}
	}

	return &MinIOStorage{client: client, bucket: cfg.MinIOBucket}, nil
}

// Upload streams a file directly to MinIO — KHÔNG ReadAll vào RAM.
// reader được pipe trực tiếp vào MinIO, không buffer toàn bộ file.
func (s *MinIOStorage) Upload(ctx context.Context, filename string, reader io.Reader, size int64, contentType string) (string, error) {
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	_, err := s.client.PutObject(ctx, s.bucket, filename, reader, size, minio.PutObjectOptions{
		ContentType: contentType,
		// Tắt multipart nếu size nhỏ (< 5MB) để đơn giản hơn
		// MinIO SDK tự handle multipart cho file lớn
	})
	if err != nil {
		return "", fmt.Errorf("failed to upload %q: %w", filename, err)
	}

	return filename, nil
}

// GetObject retrieves a file as a seekable stream từ MinIO.
//
// Dùng http.ServeContent(w, r, name, modTime, result.Body) ở handler để:
//   - Tự động handle Range/Partial Content (video seek)
//   - Không buffer toàn bộ file vào RAM
//   - Hỗ trợ If-Modified-Since, ETag caching
//
// Caller phải gọi result.Body.Close() sau khi dùng xong.
func (s *MinIOStorage) GetObject(ctx context.Context, filename string) (*ObjectResult, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, filename, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to open object %q: %w", filename, err)
	}

	// QUAN TRỌNG: GetObject() của MinIO SDK không fail ngay nếu object không tồn tại.
	// Error chỉ xuất hiện khi gọi Read() lần đầu. Dùng Stat() để check exists ngay.
	info, err := obj.Stat()
	if err != nil {
		obj.Close()
		if isNotFound(err) {
			return nil, fmt.Errorf("file not found: %s", filename)
		}
		return nil, fmt.Errorf("failed to stat object %q: %w", filename, err)
	}

	// *minio.Object implement io.ReadSeeker + io.Closer = io.ReadSeekCloser
	return &ObjectResult{
		Body:         obj,
		Size:         info.Size,
		ContentType:  info.ContentType,
		LastModified: info.LastModified,
		ETag:         info.ETag,
	}, nil
}

// Delete removes a file from MinIO.
// MinIO's RemoveObject không trả về error khi file không tồn tại,
// nên ta dùng StatObject để check trước.
func (s *MinIOStorage) Delete(ctx context.Context, filename string) error {
	// Check tồn tại trước (RemoveObject luôn success kể cả không có file)
	_, err := s.client.StatObject(ctx, s.bucket, filename, minio.StatObjectOptions{})
	if err != nil {
		if isNotFound(err) {
			return fmt.Errorf("file not found: %s", filename)
		}
		return fmt.Errorf("failed to check file %q: %w", filename, err)
	}

	if err := s.client.RemoveObject(ctx, s.bucket, filename, minio.RemoveObjectOptions{}); err != nil {
		return fmt.Errorf("failed to delete %q: %w", filename, err)
	}

	return nil
}

// isNotFound kiểm tra xem MinIO error có phải "not found" không
func isNotFound(err error) bool {
	resp := minio.ToErrorResponse(err)
	return resp.Code == "NoSuchKey" || resp.Code == "NoSuchBucket"
}