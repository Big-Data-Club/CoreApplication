package service

import (
	"context"
	"errors"

	"latex-service/internal/dto"
	"latex-service/internal/repository"
)

// CommentService manages project comments
type CommentService struct {
	commentRepo *repository.CommentRepository
	accessSvc   *AccessService
}

// NewCommentService creates a new CommentService
func NewCommentService(commentRepo *repository.CommentRepository, accessSvc *AccessService) *CommentService {
	return &CommentService{
		commentRepo: commentRepo,
		accessSvc:   accessSvc,
	}
}

// CreateComment creates a new comment. Requires Reviewer+ access (can comment but not edit).
func (s *CommentService) CreateComment(ctx context.Context, projectID, userID int64, email string, req *dto.CreateCommentRequest) (*dto.CommentResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessReviewer); err != nil {
		return nil, err
	}
	return s.commentRepo.Create(ctx, projectID, req.FileID, userID, email, req.Content,
		req.SelectionStart, req.SelectionEnd, req.SelectedText, req.ParentID)
}

// UpdateComment edits the content of a comment. Only the original author may edit.
func (s *CommentService) UpdateComment(ctx context.Context, projectID, commentID, userID int64, req *dto.UpdateCommentRequest) (*dto.CommentResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessViewer); err != nil {
		return nil, err
	}

	comment, err := s.commentRepo.GetByID(ctx, commentID)
	if err != nil {
		return nil, err
	}
	if comment.UserID != userID {
		return nil, errors.New("only the comment author can edit this comment")
	}
	return s.commentRepo.Update(ctx, commentID, req.Content)
}

// DeleteComment removes a comment. Author or project owner may delete.
func (s *CommentService) DeleteComment(ctx context.Context, projectID, commentID, userID int64) error {
	comment, err := s.commentRepo.GetByID(ctx, commentID)
	if err != nil {
		return err
	}

	// Check access: must be member and (author OR owner)
	level, err := s.accessSvc.CheckAccess(ctx, projectID, userID)
	if err != nil {
		return err
	}
	if level == AccessNone {
		return errors.New("project not found or access denied")
	}
	if comment.UserID != userID && level != AccessOwner {
		return errors.New("only the comment author or project owner can delete this comment")
	}
	return s.commentRepo.Delete(ctx, commentID)
}

// ResolveComment marks a comment as resolved. Reviewer+ may resolve.
func (s *CommentService) ResolveComment(ctx context.Context, projectID, commentID, userID int64) error {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessReviewer); err != nil {
		return err
	}
	return s.commentRepo.Resolve(ctx, commentID, userID)
}

// UnresolveComment reopens a resolved comment. Reviewer+ may unresolve.
func (s *CommentService) UnresolveComment(ctx context.Context, projectID, commentID, userID int64) error {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessReviewer); err != nil {
		return err
	}
	return s.commentRepo.Unresolve(ctx, commentID)
}

// ListByFile returns all comments for a file. Viewer+ may read.
func (s *CommentService) ListByFile(ctx context.Context, projectID, fileID, userID int64) ([]*dto.CommentResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessViewer); err != nil {
		return nil, err
	}
	return s.commentRepo.ListByFile(ctx, fileID)
}

// ListByProject returns all comments across a project. Viewer+ may read.
func (s *CommentService) ListByProject(ctx context.Context, projectID, userID int64) ([]*dto.CommentResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessViewer); err != nil {
		return nil, err
	}
	return s.commentRepo.ListByProject(ctx, projectID)
}
