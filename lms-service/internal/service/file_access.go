package service

import (
	"context"
	"errors"

	"example/hello/internal/repository"
)

var ErrFileQuota = errors.New("file storage quota exceeded")
var ErrFileAccess = errors.New("file access denied")

type fileAccessStore interface {
	Register(context.Context, string, int64, int64, bool) error
	Forget(context.Context, string) error
	Access(context.Context, string, int64) (bool, bool, error)
}
type FileAccessService struct{ store fileAccessStore }

func NewFileAccessService(store fileAccessStore) *FileAccessService {
	return &FileAccessService{store: store}
}
func (s *FileAccessService) Register(ctx context.Context, path string, owner, size int64, public bool) error {
	if owner <= 0 {
		return ErrFileAccess
	}
	err := s.store.Register(ctx, path, owner, size, public)
	if errors.Is(err, repository.ErrFileQuota) {
		return ErrFileQuota
	}
	return err
}
func (s *FileAccessService) Forget(ctx context.Context, path string) error {
	return s.store.Forget(ctx, path)
}
func (s *FileAccessService) Authorize(ctx context.Context, path string, userID int64, role string, internal, write bool) error {
	if internal || role == "ADMIN" {
		return nil
	}
	read, manage, err := s.store.Access(ctx, path, userID)
	if err != nil {
		return err
	}
	if write && !manage || !write && !read {
		return ErrFileAccess
	}
	return nil
}

type fileAuthorizer interface {
	Authorize(context.Context, string, int64, string, bool, bool) error
}

func (s *CourseService) authorizeFileLink(ctx context.Context, path string, userID int64, role string) error {
	if s.fileAccess == nil {
		return ErrFileAccess
	}
	// A private file cannot be made readable by attaching a guessed key to another course.
	return s.fileAccess.Authorize(ctx, path, userID, role, false, true)
}
