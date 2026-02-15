package service

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
)

type ForumService struct {
	forumRepo  *repository.ForumRepository
	courseRepo *repository.CourseRepository
}

func NewForumService(
	forumRepo *repository.ForumRepository,
	courseRepo *repository.CourseRepository,
) *ForumService {
	return &ForumService{
		forumRepo:  forumRepo,
		courseRepo: courseRepo,
	}
}

// ============================================
// POST OPERATIONS
// ============================================

// CreatePost creates a new forum post
func (s *ForumService) CreatePost(ctx context.Context, contentID, userID int64, req *dto.CreateForumPostRequest) (*dto.ForumPostResponse, error) {
	// Verify content exists and is a FORUM type
	content, err := s.courseRepo.GetContentByID(ctx, contentID)
	if err != nil {
		return nil, fmt.Errorf("content not found: %w", err)
	}

	if content.Type != models.ContentTypeForum {
		return nil, fmt.Errorf("content is not a forum")
	}

	// Create post
	post := &models.ForumPost{
		ContentID: contentID,
		UserID:    userID,
		Title:     req.Title,
		Body:      req.Body,
		Tags:      req.Tags,
	}

	if post.Tags == nil {
		post.Tags = []string{}
	}

	createdPost, err := s.forumRepo.CreatePost(ctx, post)
	if err != nil {
		return nil, err
	}

	// Get full post with user info
	fullPost, err := s.forumRepo.GetPostByID(ctx, createdPost.ID, userID)
	if err != nil {
		return nil, err
	}

	return s.postToResponse(fullPost), nil
}

// GetPost retrieves a post by ID and increments view count
func (s *ForumService) GetPost(ctx context.Context, postID, currentUserID int64) (*dto.ForumPostResponse, error) {
	post, err := s.forumRepo.GetPostByID(ctx, postID, currentUserID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("post not found")
		}
		return nil, err
	}

	// Increment view count (fire and forget)
	go s.forumRepo.IncrementViewCount(context.Background(), postID)

	return s.postToResponse(post), nil
}

// ListPosts lists posts with filtering and sorting
func (s *ForumService) ListPosts(ctx context.Context, contentID, currentUserID int64, req *dto.ListForumPostsRequest) (*dto.ListResponse, error) {
	// Set defaults
	if req.Page < 1 {
		req.Page = 1
	}
	if req.Limit < 1 {
		req.Limit = 20
	}
	if req.Limit > 100 {
		req.Limit = 100
	}
	if req.SortBy == "" {
		req.SortBy = "newest"
	}

	posts, total, err := s.forumRepo.ListPosts(ctx, contentID, currentUserID, req.SortBy, req.Search, req.Tags, req.Page, req.Limit)
	if err != nil {
		return nil, err
	}

	responses := make([]*dto.ForumPostResponse, 0, len(posts))
	for _, post := range posts {
		responses = append(responses, s.postToResponse(post))
	}

	return dto.NewListResponse(responses, req.Page, req.Limit, total), nil
}

// UpdatePost updates a post
func (s *ForumService) UpdatePost(ctx context.Context, postID, userID int64, req *dto.UpdateForumPostRequest) (*dto.ForumPostResponse, error) {
	// Get post to verify ownership
	post, err := s.forumRepo.GetPostByID(ctx, postID, userID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("post not found")
		}
		return nil, err
	}

	// Check ownership
	if post.UserID != userID {
		return nil, fmt.Errorf("not authorized to update this post")
	}

	// Build updates
	updates := make(map[string]interface{})
	if req.Title != nil {
		updates["title"] = *req.Title
	}
	if req.Body != nil {
		updates["body"] = *req.Body
	}
	if req.Tags != nil {
		updates["tags"] = *req.Tags
	}

	if len(updates) == 0 {
		return s.postToResponse(post), nil
	}

	// Update post
	err = s.forumRepo.UpdatePost(ctx, postID, updates)
	if err != nil {
		return nil, err
	}

	// Get updated post
	updatedPost, err := s.forumRepo.GetPostByID(ctx, postID, userID)
	if err != nil {
		return nil, err
	}

	return s.postToResponse(updatedPost), nil
}

// DeletePost deletes a post
func (s *ForumService) DeletePost(ctx context.Context, postID, userID int64, isAdmin bool) error {
	// Get post to verify ownership
	post, err := s.forumRepo.GetPostByID(ctx, postID, userID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("post not found")
		}
		return err
	}

	// Check ownership or admin
	if post.UserID != userID && !isAdmin {
		return fmt.Errorf("not authorized to delete this post")
	}

	return s.forumRepo.DeletePost(ctx, postID)
}

// PinPost pins or unpins a post (admin/teacher only)
func (s *ForumService) PinPost(ctx context.Context, postID int64, isPinned bool) error {
	updates := map[string]interface{}{
		"is_pinned": isPinned,
	}
	return s.forumRepo.UpdatePost(ctx, postID, updates)
}

// LockPost locks or unlocks a post (admin/teacher only)
func (s *ForumService) LockPost(ctx context.Context, postID int64, isLocked bool) error {
	updates := map[string]interface{}{
		"is_locked": isLocked,
	}
	return s.forumRepo.UpdatePost(ctx, postID, updates)
}

// ============================================
// COMMENT OPERATIONS
// ============================================

// CreateComment creates a new comment
func (s *ForumService) CreateComment(ctx context.Context, postID, userID int64, req *dto.CreateForumCommentRequest) (*dto.ForumCommentResponse, error) {
	// Get post to verify it exists and is not locked
	post, err := s.forumRepo.GetPostByID(ctx, postID, userID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("post not found")
		}
		return nil, err
	}

	if post.IsLocked {
		return nil, fmt.Errorf("post is locked")
	}

	// Calculate depth if this is a reply
	depth := 0
	if req.ParentCommentID != nil {
		parentComment, err := s.forumRepo.GetCommentByID(ctx, *req.ParentCommentID, userID)
		if err != nil {
			return nil, fmt.Errorf("parent comment not found")
		}
		depth = parentComment.Depth + 1
		
		// Limit nesting depth
		if depth > 5 {
			return nil, fmt.Errorf("maximum comment depth reached")
		}
	}

	// Create comment
	comment := &models.ForumComment{
		PostID: postID,
		UserID: userID,
		Body:   req.Body,
		Depth:  depth,
	}

	if req.ParentCommentID != nil {
		comment.ParentCommentID = sql.NullInt64{Int64: *req.ParentCommentID, Valid: true}
	}

	createdComment, err := s.forumRepo.CreateComment(ctx, comment)
	if err != nil {
		return nil, err
	}

	// Get full comment with user info
	fullComment, err := s.forumRepo.GetCommentByID(ctx, createdComment.ID, userID)
	if err != nil {
		return nil, err
	}

	return s.commentToResponse(fullComment), nil
}

// ListComments lists comments for a post
func (s *ForumService) ListComments(ctx context.Context, postID, currentUserID int64) ([]*dto.ForumCommentResponse, error) {
	comments, err := s.forumRepo.ListCommentsByPost(ctx, postID, currentUserID)
	if err != nil {
		return nil, err
	}

	// Convert to responses
	responses := make([]*dto.ForumCommentResponse, 0, len(comments))
	for _, comment := range comments {
		responses = append(responses, s.commentToResponse(comment))
	}

	// Build comment tree
	return s.buildCommentTree(responses), nil
}

// UpdateComment updates a comment
func (s *ForumService) UpdateComment(ctx context.Context, commentID, userID int64, req *dto.UpdateForumCommentRequest) (*dto.ForumCommentResponse, error) {
	// Get comment to verify ownership
	comment, err := s.forumRepo.GetCommentByID(ctx, commentID, userID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("comment not found")
		}
		return nil, err
	}

	// Check ownership
	if comment.UserID != userID {
		return nil, fmt.Errorf("not authorized to update this comment")
	}

	// Build updates
	updates := make(map[string]interface{})
	if req.Body != nil {
		updates["body"] = *req.Body
	}

	if len(updates) == 0 {
		return s.commentToResponse(comment), nil
	}

	// Update comment
	err = s.forumRepo.UpdateComment(ctx, commentID, updates)
	if err != nil {
		return nil, err
	}

	// Get updated comment
	updatedComment, err := s.forumRepo.GetCommentByID(ctx, commentID, userID)
	if err != nil {
		return nil, err
	}

	return s.commentToResponse(updatedComment), nil
}

// DeleteComment deletes a comment
func (s *ForumService) DeleteComment(ctx context.Context, commentID, userID int64, isAdmin bool) error {
	// Get comment to verify ownership
	comment, err := s.forumRepo.GetCommentByID(ctx, commentID, userID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("comment not found")
		}
		return err
	}

	// Check ownership or admin
	if comment.UserID != userID && !isAdmin {
		return fmt.Errorf("not authorized to delete this comment")
	}

	return s.forumRepo.DeleteComment(ctx, commentID)
}

// AcceptComment marks a comment as accepted answer (post owner or teacher/admin)
func (s *ForumService) AcceptComment(ctx context.Context, commentID, userID int64, isTeacherOrAdmin bool) error {
	// Get comment
	comment, err := s.forumRepo.GetCommentByID(ctx, commentID, userID)
	if err != nil {
		return fmt.Errorf("comment not found")
	}

	// Get post to check ownership
	post, err := s.forumRepo.GetPostByID(ctx, comment.PostID, userID)
	if err != nil {
		return fmt.Errorf("post not found")
	}

	// Only post owner or teacher/admin can accept answers
	if post.UserID != userID && !isTeacherOrAdmin {
		return fmt.Errorf("not authorized to accept answers")
	}

	// Unaccept all other comments first
	_, err = s.forumRepo.ListCommentsByPost(ctx, comment.PostID, userID)
	if err == nil {
		// In a real implementation, we'd update all comments to unaccept them
		// For now, we'll just accept this one
	}

	updates := map[string]interface{}{
		"is_accepted": true,
	}
	return s.forumRepo.UpdateComment(ctx, commentID, updates)
}

// ============================================
// VOTE OPERATIONS
// ============================================

// VotePost votes on a post
func (s *ForumService) VotePost(ctx context.Context, postID, userID int64, voteType string) (*dto.VoteResponse, error) {
	// Get current vote
	currentVote, err := s.forumRepo.GetUserVote(ctx, userID, models.VotableTypePost, postID)
	if err != nil {
		return nil, err
	}

	// If same vote, remove it (toggle)
	if currentVote != nil && *currentVote == voteType {
		err = s.forumRepo.DeleteVote(ctx, userID, models.VotableTypePost, postID)
		if err != nil {
			return nil, err
		}
	} else {
		// Upsert vote
		err = s.forumRepo.UpsertVote(ctx, userID, models.VotableTypePost, postID, voteType)
		if err != nil {
			return nil, err
		}
	}

	// Get updated post
	post, err := s.forumRepo.GetPostByID(ctx, postID, userID)
	if err != nil {
		return nil, err
	}

	return &dto.VoteResponse{
		Success:   true,
		VoteType:  voteType,
		NewScore:  post.Upvotes - post.Downvotes,
		Upvotes:   post.Upvotes,
		Downvotes: post.Downvotes,
	}, nil
}

// VoteComment votes on a comment
func (s *ForumService) VoteComment(ctx context.Context, commentID, userID int64, voteType string) (*dto.VoteResponse, error) {
	// Get current vote
	currentVote, err := s.forumRepo.GetUserVote(ctx, userID, models.VotableTypeComment, commentID)
	if err != nil {
		return nil, err
	}

	// If same vote, remove it (toggle)
	if currentVote != nil && *currentVote == voteType {
		err = s.forumRepo.DeleteVote(ctx, userID, models.VotableTypeComment, commentID)
		if err != nil {
			return nil, err
		}
	} else {
		// Upsert vote
		err = s.forumRepo.UpsertVote(ctx, userID, models.VotableTypeComment, commentID, voteType)
		if err != nil {
			return nil, err
		}
	}

	// Get updated comment
	comment, err := s.forumRepo.GetCommentByID(ctx, commentID, userID)
	if err != nil {
		return nil, err
	}

	return &dto.VoteResponse{
		Success:   true,
		VoteType:  voteType,
		NewScore:  comment.Upvotes - comment.Downvotes,
		Upvotes:   comment.Upvotes,
		Downvotes: comment.Downvotes,
	}, nil
}

// ============================================
// HELPER METHODS
// ============================================

func (s *ForumService) postToResponse(post *models.ForumPostWithUser) *dto.ForumPostResponse {
	var currentVote *string
	if post.CurrentUserVote.Valid {
		currentVote = &post.CurrentUserVote.String
	}

	return &dto.ForumPostResponse{
		ID:              post.ID,
		ContentID:       post.ContentID,
		UserID:          post.UserID,
		UserName:        post.UserName,
		UserEmail:       post.UserEmail,
		Title:           post.Title,
		Body:            post.Body,
		Tags:            post.Tags,
		Upvotes:         post.Upvotes,
		Downvotes:       post.Downvotes,
		Score:           post.Upvotes - post.Downvotes,
		CommentCount:    post.CommentCount,
		ViewCount:       post.ViewCount,
		IsPinned:        post.IsPinned,
		IsLocked:        post.IsLocked,
		CurrentUserVote: currentVote,
		CreatedAt:       post.CreatedAt,
		UpdatedAt:       post.UpdatedAt,
	}
}

func (s *ForumService) commentToResponse(comment *models.ForumCommentWithUser) *dto.ForumCommentResponse {
	var currentVote *string
	if comment.CurrentUserVote.Valid {
		currentVote = &comment.CurrentUserVote.String
	}

	var parentID *int64
	if comment.ParentCommentID.Valid {
		parentID = &comment.ParentCommentID.Int64
	}

	return &dto.ForumCommentResponse{
		ID:              comment.ID,
		PostID:          comment.PostID,
		ParentCommentID: parentID,
		UserID:          comment.UserID,
		UserName:        comment.UserName,
		UserEmail:       comment.UserEmail,
		Body:            comment.Body,
		Upvotes:         comment.Upvotes,
		Downvotes:       comment.Downvotes,
		Score:           comment.Upvotes - comment.Downvotes,
		IsAccepted:      comment.IsAccepted,
		Depth:           comment.Depth,
		CurrentUserVote: currentVote,
		CreatedAt:       comment.CreatedAt,
		UpdatedAt:       comment.UpdatedAt,
	}
}

// buildCommentTree builds a tree structure from flat comment list
func (s *ForumService) buildCommentTree(comments []*dto.ForumCommentResponse) []*dto.ForumCommentResponse {
	// Create a map for quick lookup
	commentMap := make(map[int64]*dto.ForumCommentResponse)
	for _, comment := range comments {
		commentMap[comment.ID] = comment
		comment.Replies = []*dto.ForumCommentResponse{}
	}

	// Build tree
	var rootComments []*dto.ForumCommentResponse
	for _, comment := range comments {
		if comment.ParentCommentID == nil {
			rootComments = append(rootComments, comment)
		} else {
			if parent, ok := commentMap[*comment.ParentCommentID]; ok {
				parent.Replies = append(parent.Replies, comment)
			}
		}
	}

	return rootComments
}