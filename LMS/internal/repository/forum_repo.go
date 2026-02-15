package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"

	"example/hello/internal/models"
	"github.com/lib/pq"
)

type ForumRepository struct {
	db *sql.DB
}

func NewForumRepository(db *sql.DB) *ForumRepository {
	return &ForumRepository{db: db}
}

// ============================================
// POST OPERATIONS
// ============================================

// CreatePost creates a new forum post
func (r *ForumRepository) CreatePost(ctx context.Context, post *models.ForumPost) (*models.ForumPost, error) {
	query := `
		INSERT INTO forum_posts (content_id, user_id, title, body, tags)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRowContext(ctx, query,
		post.ContentID,
		post.UserID,
		post.Title,
		post.Body,
		pq.Array(post.Tags),
	).Scan(&post.ID, &post.CreatedAt, &post.UpdatedAt)

	if err != nil {
		return nil, err
	}

	return post, nil
}

// GetPostByID retrieves a post by ID with user info and current user's vote
func (r *ForumRepository) GetPostByID(ctx context.Context, postID, currentUserID int64) (*models.ForumPostWithUser, error) {
	query := `
		SELECT 
			p.id, p.content_id, p.user_id, p.title, p.body, p.tags,
			p.upvotes, p.downvotes, p.comment_count, p.view_count,
			p.is_pinned, p.is_locked, p.created_at, p.updated_at,
			u.full_name as user_name, u.email as user_email,
			v.vote_type as current_user_vote
		FROM forum_posts p
		LEFT JOIN users u ON p.user_id = u.id
		LEFT JOIN forum_votes v ON v.votable_type = 'post' 
			AND v.votable_id = p.id 
			AND v.user_id = $2
		WHERE p.id = $1
	`

	var post models.ForumPostWithUser
	var tags pq.StringArray

	err := r.db.QueryRowContext(ctx, query, postID, currentUserID).Scan(
		&post.ID,
		&post.ContentID,
		&post.UserID,
		&post.Title,
		&post.Body,
		&tags,
		&post.Upvotes,
		&post.Downvotes,
		&post.CommentCount,
		&post.ViewCount,
		&post.IsPinned,
		&post.IsLocked,
		&post.CreatedAt,
		&post.UpdatedAt,
		&post.UserName,
		&post.UserEmail,
		&post.CurrentUserVote,
	)

	if err != nil {
		return nil, err
	}

	post.Tags = tags
	return &post, nil
}

// ListPosts lists posts with sorting, filtering, and pagination
func (r *ForumRepository) ListPosts(ctx context.Context, contentID, currentUserID int64, sortBy, search, tags string, page, limit int) ([]*models.ForumPostWithUser, int, error) {
	// Build WHERE clause
	where := []string{"p.content_id = $1"}
	args := []interface{}{contentID}
	argIndex := 2

	// Add search filter
	if search != "" {
		where = append(where, fmt.Sprintf("to_tsvector('english', p.title || ' ' || p.body) @@ plainto_tsquery('english', $%d)", argIndex))
		args = append(args, search)
		argIndex++
	}

	// Add tags filter
	if tags != "" {
		tagList := strings.Split(tags, ",")
		where = append(where, fmt.Sprintf("p.tags && $%d", argIndex))
		args = append(args, pq.Array(tagList))
		argIndex++
	}

	whereClause := strings.Join(where, " AND ")

	// Determine sort order
	var orderBy string
	switch sortBy {
	case "votes":
		orderBy = "p.is_pinned DESC, (p.upvotes - p.downvotes) DESC, p.created_at DESC"
	case "oldest":
		orderBy = "p.is_pinned DESC, p.created_at ASC"
	case "views":
		orderBy = "p.is_pinned DESC, p.view_count DESC, p.created_at DESC"
	default: // newest
		orderBy = "p.is_pinned DESC, p.created_at DESC"
	}

	// Count total
	countQuery := fmt.Sprintf("SELECT COUNT(*) FROM forum_posts p WHERE %s", whereClause)
	var total int
	err := r.db.QueryRowContext(ctx, countQuery, args...).Scan(&total)
	if err != nil {
		return nil, 0, err
	}

	// Calculate offset
	offset := (page - 1) * limit

	// Get posts
	query := fmt.Sprintf(`
		SELECT 
			p.id, p.content_id, p.user_id, p.title, p.body, p.tags,
			p.upvotes, p.downvotes, p.comment_count, p.view_count,
			p.is_pinned, p.is_locked, p.created_at, p.updated_at,
			u.full_name as user_name, u.email as user_email,
			v.vote_type as current_user_vote
		FROM forum_posts p
		LEFT JOIN users u ON p.user_id = u.id
		LEFT JOIN forum_votes v ON v.votable_type = 'post' 
			AND v.votable_id = p.id 
			AND v.user_id = $%d
		WHERE %s
		ORDER BY %s
		LIMIT $%d OFFSET $%d
	`, argIndex, whereClause, orderBy, argIndex+1, argIndex+2)

	args = append(args, currentUserID, limit, offset)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var posts []*models.ForumPostWithUser
	for rows.Next() {
		var post models.ForumPostWithUser
		var tags pq.StringArray

		err := rows.Scan(
			&post.ID,
			&post.ContentID,
			&post.UserID,
			&post.Title,
			&post.Body,
			&tags,
			&post.Upvotes,
			&post.Downvotes,
			&post.CommentCount,
			&post.ViewCount,
			&post.IsPinned,
			&post.IsLocked,
			&post.CreatedAt,
			&post.UpdatedAt,
			&post.UserName,
			&post.UserEmail,
			&post.CurrentUserVote,
		)
		if err != nil {
			return nil, 0, err
		}

		post.Tags = tags
		posts = append(posts, &post)
	}

	return posts, total, rows.Err()
}

// UpdatePost updates a post
func (r *ForumRepository) UpdatePost(ctx context.Context, postID int64, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	query := "UPDATE forum_posts SET "
	args := []interface{}{}
	argCount := 1

	for field, value := range updates {
		if argCount > 1 {
			query += ", "
		}
		query += fmt.Sprintf("%s = $%d", field, argCount)
		
		// Handle pq.Array for tags
		if field == "tags" {
			if tags, ok := value.([]string); ok {
				args = append(args, pq.Array(tags))
			} else {
				args = append(args, value)
			}
		} else {
			args = append(args, value)
		}
		argCount++
	}

	query += fmt.Sprintf(" WHERE id = $%d", argCount)
	args = append(args, postID)

	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// DeletePost deletes a post
func (r *ForumRepository) DeletePost(ctx context.Context, postID int64) error {
	query := `DELETE FROM forum_posts WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, postID)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// IncrementViewCount increments the view count
func (r *ForumRepository) IncrementViewCount(ctx context.Context, postID int64) error {
	query := `UPDATE forum_posts SET view_count = view_count + 1 WHERE id = $1`
	_, err := r.db.ExecContext(ctx, query, postID)
	return err
}

// ============================================
// COMMENT OPERATIONS
// ============================================

// CreateComment creates a new comment
func (r *ForumRepository) CreateComment(ctx context.Context, comment *models.ForumComment) (*models.ForumComment, error) {
	query := `
		INSERT INTO forum_comments (post_id, parent_comment_id, user_id, body, depth)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRowContext(ctx, query,
		comment.PostID,
		comment.ParentCommentID,
		comment.UserID,
		comment.Body,
		comment.Depth,
	).Scan(&comment.ID, &comment.CreatedAt, &comment.UpdatedAt)

	if err != nil {
		return nil, err
	}

	return comment, nil
}

// GetCommentByID retrieves a comment by ID
func (r *ForumRepository) GetCommentByID(ctx context.Context, commentID, currentUserID int64) (*models.ForumCommentWithUser, error) {
	query := `
		SELECT 
			c.id, c.post_id, c.parent_comment_id, c.user_id, c.body,
			c.upvotes, c.downvotes, c.is_accepted, c.depth,
			c.created_at, c.updated_at,
			u.full_name as user_name, u.email as user_email,
			v.vote_type as current_user_vote
		FROM forum_comments c
		LEFT JOIN users u ON c.user_id = u.id
		LEFT JOIN forum_votes v ON v.votable_type = 'comment' 
			AND v.votable_id = c.id 
			AND v.user_id = $2
		WHERE c.id = $1
	`

	var comment models.ForumCommentWithUser

	err := r.db.QueryRowContext(ctx, query, commentID, currentUserID).Scan(
		&comment.ID,
		&comment.PostID,
		&comment.ParentCommentID,
		&comment.UserID,
		&comment.Body,
		&comment.Upvotes,
		&comment.Downvotes,
		&comment.IsAccepted,
		&comment.Depth,
		&comment.CreatedAt,
		&comment.UpdatedAt,
		&comment.UserName,
		&comment.UserEmail,
		&comment.CurrentUserVote,
	)

	if err != nil {
		return nil, err
	}

	return &comment, nil
}

// ListCommentsByPost retrieves all comments for a post (flat list, frontend will build tree)
func (r *ForumRepository) ListCommentsByPost(ctx context.Context, postID, currentUserID int64) ([]*models.ForumCommentWithUser, error) {
	query := `
		SELECT 
			c.id, c.post_id, c.parent_comment_id, c.user_id, c.body,
			c.upvotes, c.downvotes, c.is_accepted, c.depth,
			c.created_at, c.updated_at,
			u.full_name as user_name, u.email as user_email,
			v.vote_type as current_user_vote
		FROM forum_comments c
		LEFT JOIN users u ON c.user_id = u.id
		LEFT JOIN forum_votes v ON v.votable_type = 'comment' 
			AND v.votable_id = c.id 
			AND v.user_id = $2
		WHERE c.post_id = $1
		ORDER BY c.is_accepted DESC, (c.upvotes - c.downvotes) DESC, c.created_at ASC
	`

	rows, err := r.db.QueryContext(ctx, query, postID, currentUserID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var comments []*models.ForumCommentWithUser
	for rows.Next() {
		var comment models.ForumCommentWithUser

		err := rows.Scan(
			&comment.ID,
			&comment.PostID,
			&comment.ParentCommentID,
			&comment.UserID,
			&comment.Body,
			&comment.Upvotes,
			&comment.Downvotes,
			&comment.IsAccepted,
			&comment.Depth,
			&comment.CreatedAt,
			&comment.UpdatedAt,
			&comment.UserName,
			&comment.UserEmail,
			&comment.CurrentUserVote,
		)
		if err != nil {
			return nil, err
		}

		comments = append(comments, &comment)
	}

	return comments, rows.Err()
}

// UpdateComment updates a comment
func (r *ForumRepository) UpdateComment(ctx context.Context, commentID int64, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	query := "UPDATE forum_comments SET "
	args := []interface{}{}
	argCount := 1

	for field, value := range updates {
		if argCount > 1 {
			query += ", "
		}
		query += fmt.Sprintf("%s = $%d", field, argCount)
		args = append(args, value)
		argCount++
	}

	query += fmt.Sprintf(" WHERE id = $%d", argCount)
	args = append(args, commentID)

	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// DeleteComment deletes a comment
func (r *ForumRepository) DeleteComment(ctx context.Context, commentID int64) error {
	query := `DELETE FROM forum_comments WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, commentID)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// ============================================
// VOTE OPERATIONS
// ============================================

// UpsertVote creates or updates a vote
func (r *ForumRepository) UpsertVote(ctx context.Context, userID int64, votableType string, votableID int64, voteType string) error {
	query := `
		INSERT INTO forum_votes (user_id, votable_type, votable_id, vote_type)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (user_id, votable_type, votable_id)
		DO UPDATE SET vote_type = $4
	`

	_, err := r.db.ExecContext(ctx, query, userID, votableType, votableID, voteType)
	return err
}

// DeleteVote deletes a vote
func (r *ForumRepository) DeleteVote(ctx context.Context, userID int64, votableType string, votableID int64) error {
	query := `DELETE FROM forum_votes WHERE user_id = $1 AND votable_type = $2 AND votable_id = $3`

	_, err := r.db.ExecContext(ctx, query, userID, votableType, votableID)
	return err
}

// GetUserVote gets the user's vote on a votable
func (r *ForumRepository) GetUserVote(ctx context.Context, userID int64, votableType string, votableID int64) (*string, error) {
	query := `SELECT vote_type FROM forum_votes WHERE user_id = $1 AND votable_type = $2 AND votable_id = $3`

	var voteType string
	err := r.db.QueryRowContext(ctx, query, userID, votableType, votableID).Scan(&voteType)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	return &voteType, nil
}