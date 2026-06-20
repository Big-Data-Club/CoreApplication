package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"
)

const defaultPageSize = 50

// Channel represents a chat channel row.
type Channel struct {
	ID          int64
	Slug        string
	Name        string
	Description string
	IsPrivate   bool
	IsDM        bool
	CreatedBy   int64
	CreatedAt   time.Time
}

// ChannelRole is one row in chat_channel_roles.
type ChannelRole struct {
	ChannelID int64
	RoleName  string
	CanRead   bool
	CanWrite  bool
}

// Message is one row in chat_messages enriched with sender data.
type Message struct {
	ID             int64
	ChannelID      int64
	SenderID       int64
	SenderName     string
	SenderEmail    string
	SenderAvatar   string
	Body           string
	IsDeleted      bool
	CreatedAt      time.Time
}

// ChatRepository handles all chat-domain DB operations.
type ChatRepository struct {
	db *sql.DB
}

func NewChatRepository(db *sql.DB) *ChatRepository {
	return &ChatRepository{db: db}
}

// ─── Channels ─────────────────────────────────────────────────────────────────

// ListAccessibleChannels returns channels the caller may read.
// A channel is accessible if:
//   - It is not private (is_private = false), AND has a role entry matching one of userRoles, OR
//   - The caller's userID is in chat_channel_users (whitelist), OR
//   - The caller has ADMIN role (sees all)
func (r *ChatRepository) ListAccessibleChannels(
	ctx context.Context,
	userID int64,
	userRoles []string,
) ([]Channel, error) {
	isAdmin := false
	for _, role := range userRoles {
		if role == "ADMIN" {
			isAdmin = true
			break
		}
	}

	var (
		rows *sql.Rows
		err  error
	)

	if isAdmin {
		rows, err = r.db.QueryContext(ctx, `
			SELECT id, slug, name, description, is_private, is_dm, created_by, created_at
			FROM chat_channels c
			WHERE c.is_dm = false
			   OR (c.is_dm = true AND EXISTS (
			       SELECT 1 FROM chat_channel_users ccu
			       WHERE ccu.channel_id = c.id AND ccu.user_id = $1
			   ))
			ORDER BY created_at ASC
		`, userID)
	} else {
		// Build role placeholder list: $2, $3, ...
		placeholders, args := buildRoleArgs(userID, userRoles)
		query := fmt.Sprintf(`
			SELECT DISTINCT c.id, c.slug, c.name, c.description, c.is_private, c.is_dm, c.created_by, c.created_at
			FROM chat_channels c
			WHERE (
				(c.is_dm = false AND (
					EXISTS (
						SELECT 1 FROM chat_channel_roles ccr
						WHERE ccr.channel_id = c.id
						  AND ccr.can_read = true
						  AND ccr.role_name IN (%s)
					)
					OR EXISTS (
						SELECT 1 FROM chat_channel_users ccu
						WHERE ccu.channel_id = c.id
						  AND ccu.user_id = $1
					)
				))
				OR (c.is_dm = true AND EXISTS (
					SELECT 1 FROM chat_channel_users ccu
					WHERE ccu.channel_id = c.id
					  AND ccu.user_id = $1
				))
			)
			ORDER BY c.created_at ASC
		`, placeholders)
		rows, err = r.db.QueryContext(ctx, query, args...)
	}

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var channels []Channel
	for rows.Next() {
		var ch Channel
		if err := rows.Scan(
			&ch.ID, &ch.Slug, &ch.Name, &ch.Description,
			&ch.IsPrivate, &ch.IsDM, &ch.CreatedBy, &ch.CreatedAt,
		); err != nil {
			return nil, err
		}
		channels = append(channels, ch)
	}
	return channels, rows.Err()
}

// GetChannelByID fetches a single channel.
func (r *ChatRepository) GetChannelByID(ctx context.Context, id int64) (*Channel, error) {
	ch := &Channel{}
	err := r.db.QueryRowContext(ctx, `
		SELECT id, slug, name, description, is_private, is_dm, created_by, created_at
		FROM chat_channels WHERE id = $1
	`, id).Scan(
		&ch.ID, &ch.Slug, &ch.Name, &ch.Description,
		&ch.IsPrivate, &ch.IsDM, &ch.CreatedBy, &ch.CreatedAt,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return ch, err
}

// CreateChannel inserts a new channel. Returns the created Channel.
func (r *ChatRepository) CreateChannel(
	ctx context.Context,
	slug, name, description string,
	isPrivate bool,
	createdBy int64,
) (*Channel, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback() }()

	ch := &Channel{}
	err = tx.QueryRowContext(ctx, `
		INSERT INTO chat_channels (slug, name, description, is_private, is_dm, created_by)
		VALUES ($1, $2, $3, $4, false, $5)
		RETURNING id, slug, name, description, is_private, is_dm, created_by, created_at
	`, slug, name, description, isPrivate, createdBy).Scan(
		&ch.ID, &ch.Slug, &ch.Name, &ch.Description,
		&ch.IsPrivate, &ch.IsDM, &ch.CreatedBy, &ch.CreatedAt,
	)
	if err != nil {
		return nil, err
	}

	// For public channels (isPrivate = false), automatically grant read+write to all standard roles
	// For private channels, automatically grant read+write to ADMIN so they can configure it
	rolesToSeed := []string{"ADMIN"}
	if !isPrivate {
		rolesToSeed = append(rolesToSeed, "TEACHER", "STUDENT")
	}

	for _, role := range rolesToSeed {
		_, err = tx.ExecContext(ctx, `
			INSERT INTO chat_channel_roles (channel_id, role_name, can_read, can_write)
			VALUES ($1, $2, true, true)
		`, ch.ID, role)
		if err != nil {
			return nil, fmt.Errorf("seed role %s: %w", role, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return nil, err
	}

	return ch, nil
}

// UpdateChannel updates name/description/is_private.
func (r *ChatRepository) UpdateChannel(
	ctx context.Context,
	id int64,
	name, description string,
	isPrivate bool,
) (*Channel, error) {
	ch := &Channel{}
	err := r.db.QueryRowContext(ctx, `
		UPDATE chat_channels
		SET name = $2, description = $3, is_private = $4
		WHERE id = $1
		RETURNING id, slug, name, description, is_private, is_dm, created_by, created_at
	`, id, name, description, isPrivate).Scan(
		&ch.ID, &ch.Slug, &ch.Name, &ch.Description,
		&ch.IsPrivate, &ch.IsDM, &ch.CreatedBy, &ch.CreatedAt,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return ch, err
}

// GetOrCreateDMChannel finds an existing DM channel between user1ID and user2ID,
// or creates one if it doesn't exist.
func (r *ChatRepository) GetOrCreateDMChannel(ctx context.Context, user1ID, user2ID int64) (*Channel, error) {
	// First, try to find an existing DM channel where both users are whitelisted.
	ch := &Channel{}
	err := r.db.QueryRowContext(ctx, `
		SELECT c.id, c.slug, c.name, c.description, c.is_private, c.is_dm, c.created_by, c.created_at
		FROM chat_channels c
		JOIN chat_channel_users ccu1 ON ccu1.channel_id = c.id AND ccu1.user_id = $1
		JOIN chat_channel_users ccu2 ON ccu2.channel_id = c.id AND ccu2.user_id = $2
		WHERE c.is_dm = true
		LIMIT 1
	`, user1ID, user2ID).Scan(
		&ch.ID, &ch.Slug, &ch.Name, &ch.Description,
		&ch.IsPrivate, &ch.IsDM, &ch.CreatedBy, &ch.CreatedAt,
	)
	if err == nil {
		return ch, nil
	}
	if err != sql.ErrNoRows {
		return nil, fmt.Errorf("find existing dm: %w", err)
	}

	// Not found, we must create a new DM channel in a transaction.
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback() }()

	// Generate a unique slug: dm:min_id:max_id
	minID := user1ID
	maxID := user2ID
	if minID > maxID {
		minID, maxID = maxID, minID
	}
	slug := fmt.Sprintf("dm:%d:%d", minID, maxID)
	name := "Direct Message"
	description := fmt.Sprintf("Direct Message between user %d and %d", minID, maxID)

	// Insert channel record
	err = tx.QueryRowContext(ctx, `
		INSERT INTO chat_channels (slug, name, description, is_private, is_dm, created_by)
		VALUES ($1, $2, $3, true, true, $4)
		ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug
		RETURNING id, slug, name, description, is_private, is_dm, created_by, created_at
	`, slug, name, description, user1ID).Scan(
		&ch.ID, &ch.Slug, &ch.Name, &ch.Description,
		&ch.IsPrivate, &ch.IsDM, &ch.CreatedBy, &ch.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("create dm channel: %w", err)
	}

	// Insert both participants to chat_channel_users
	_, err = tx.ExecContext(ctx, `
		INSERT INTO chat_channel_users (channel_id, user_id)
		VALUES ($1, $2), ($1, $3)
		ON CONFLICT DO NOTHING
	`, ch.ID, user1ID, user2ID)
	if err != nil {
		return nil, fmt.Errorf("insert dm participants: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit dm tx: %w", err)
	}

	return ch, nil
}

// DeleteChannel removes a channel (cascades to messages, roles, users).
func (r *ChatRepository) DeleteChannel(ctx context.Context, id int64) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM chat_channels WHERE id = $1`, id)
	return err
}

// ─── Channel Roles ────────────────────────────────────────────────────────────

// GetChannelRoles returns all role entries for a channel.
func (r *ChatRepository) GetChannelRoles(ctx context.Context, channelID int64) ([]ChannelRole, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT channel_id, role_name, can_read, can_write
		FROM chat_channel_roles
		WHERE channel_id = $1
	`, channelID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var roles []ChannelRole
	for rows.Next() {
		var cr ChannelRole
		if err := rows.Scan(&cr.ChannelID, &cr.RoleName, &cr.CanRead, &cr.CanWrite); err != nil {
			return nil, err
		}
		roles = append(roles, cr)
	}
	return roles, rows.Err()
}

// SetChannelRoles replaces all role entries for a channel atomically.
func (r *ChatRepository) SetChannelRoles(ctx context.Context, channelID int64, roles []ChannelRole) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx,
		`DELETE FROM chat_channel_roles WHERE channel_id = $1`, channelID,
	); err != nil {
		return err
	}

	if len(roles) > 0 {
		stmt, err := tx.PrepareContext(ctx, `
			INSERT INTO chat_channel_roles (channel_id, role_name, can_read, can_write)
			VALUES ($1, $2, $3, $4)
		`)
		if err != nil {
			return err
		}
		defer stmt.Close()

		for _, role := range roles {
			if _, err := stmt.ExecContext(ctx,
				channelID, role.RoleName, role.CanRead, role.CanWrite,
			); err != nil {
				return err
			}
		}
	}

	return tx.Commit()
}

// ─── Channel User Whitelist ────────────────────────────────────────────────────

// GetChannelUsers returns the whitelisted user IDs for a channel.
func (r *ChatRepository) GetChannelUsers(ctx context.Context, channelID int64) ([]int64, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT user_id FROM chat_channel_users WHERE channel_id = $1`, channelID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// SetChannelUsers replaces the whitelist for a channel atomically.
func (r *ChatRepository) SetChannelUsers(ctx context.Context, channelID int64, userIDs []int64) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx,
		`DELETE FROM chat_channel_users WHERE channel_id = $1`, channelID,
	); err != nil {
		return err
	}

	for _, uid := range userIDs {
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO chat_channel_users (channel_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
			channelID, uid,
		); err != nil {
			return fmt.Errorf("whitelist user %d: %w", uid, err)
		}
	}

	return tx.Commit()
}

// GetChannelUsersWithDetails returns the whitelisted users for a channel with full
// profile details joined in a single query — no N+1 issue regardless of list size.
func (r *ChatRepository) GetChannelUsersWithDetails(ctx context.Context, channelID int64) ([]User, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT u.id, u.email, u.full_name, u.profile_picture
		FROM users u
		JOIN chat_channel_users ccu ON ccu.user_id = u.id
		WHERE ccu.channel_id = $1
		ORDER BY u.full_name ASC
	`, channelID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var users []User
	for rows.Next() {
		var u User
		var pic sql.NullString
		if err := rows.Scan(&u.ID, &u.Email, &u.FullName, &pic); err != nil {
			return nil, err
		}
		u.ProfilePicture = pic.String
		users = append(users, u)
	}
	return users, rows.Err()
}

// CanUserAccess returns (canRead, canWrite) for the given channel+user+roles combination.
func (r *ChatRepository) CanUserAccess(
	ctx context.Context,
	channelID, userID int64,
	userRoles []string,
) (canRead, canWrite bool, err error) {
	// Admin can always access
	for _, role := range userRoles {
		if role == "ADMIN" {
			return true, true, nil
		}
	}

	// Check user whitelist
	var inWhitelist bool
	if err = r.db.QueryRowContext(ctx, `
		SELECT EXISTS(SELECT 1 FROM chat_channel_users WHERE channel_id=$1 AND user_id=$2)
	`, channelID, userID).Scan(&inWhitelist); err != nil {
		return
	}
	if inWhitelist {
		return true, true, nil
	}

	// Check role permissions — aggregate max permissions across all matching roles
	if len(userRoles) == 0 {
		return false, false, nil
	}
	placeholders, args := buildRoleArgs(channelID, userRoles)
	query := fmt.Sprintf(`
		SELECT BOOL_OR(can_read), BOOL_OR(can_write)
		FROM chat_channel_roles
		WHERE channel_id = $1 AND role_name IN (%s)
	`, placeholders)

	var r1, w1 sql.NullBool
	if err = r.db.QueryRowContext(ctx, query, args...).Scan(&r1, &w1); err != nil {
		return
	}
	return r1.Bool, w1.Bool, nil
}

// ─── Messages ─────────────────────────────────────────────────────────────────

// ListMessages returns up to `limit` messages before `beforeID` (cursor pagination).
// If beforeID == 0, returns the latest `limit` messages.
// Results are returned oldest-first within the page for chronological display.
func (r *ChatRepository) ListMessages(
	ctx context.Context,
	channelID, beforeID int64,
	limit int,
) ([]Message, error) {
	if limit <= 0 || limit > 100 {
		limit = defaultPageSize
	}

	var (
		rows *sql.Rows
		err  error
	)

	// We fetch newest-first using a cursor, then reverse in code for display order.
	if beforeID > 0 {
		rows, err = r.db.QueryContext(ctx, `
			SELECT m.id, m.channel_id, m.sender_id,
			       COALESCE(u.full_name, u.email) AS sender_name,
			       u.email                         AS sender_email,
			       COALESCE(u.profile_picture, '')  AS sender_avatar,
			       CASE WHEN m.is_deleted THEN '[deleted]' ELSE m.body END AS body,
			       m.is_deleted, m.created_at
			FROM chat_messages m
			JOIN users u ON u.id = m.sender_id
			WHERE m.channel_id = $1 AND m.id < $2
			ORDER BY m.id DESC
			LIMIT $3
		`, channelID, beforeID, limit)
	} else {
		rows, err = r.db.QueryContext(ctx, `
			SELECT m.id, m.channel_id, m.sender_id,
			       COALESCE(u.full_name, u.email) AS sender_name,
			       u.email                         AS sender_email,
			       COALESCE(u.profile_picture, '')  AS sender_avatar,
			       CASE WHEN m.is_deleted THEN '[deleted]' ELSE m.body END AS body,
			       m.is_deleted, m.created_at
			FROM chat_messages m
			JOIN users u ON u.id = m.sender_id
			WHERE m.channel_id = $1
			ORDER BY m.id DESC
			LIMIT $2
		`, channelID, limit)
	}

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var msgs []Message
	for rows.Next() {
		var msg Message
		if err := rows.Scan(
			&msg.ID, &msg.ChannelID, &msg.SenderID,
			&msg.SenderName, &msg.SenderEmail, &msg.SenderAvatar,
			&msg.Body, &msg.IsDeleted, &msg.CreatedAt,
		); err != nil {
			return nil, err
		}
		msgs = append(msgs, msg)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	// Reverse to chronological order
	for i, j := 0, len(msgs)-1; i < j; i, j = i+1, j-1 {
		msgs[i], msgs[j] = msgs[j], msgs[i]
	}

	return msgs, nil
}

// CreateMessage inserts a new message and returns it with sender info.
func (r *ChatRepository) CreateMessage(
	ctx context.Context,
	channelID, senderID int64,
	body string,
) (*Message, error) {
	var msgID int64
	var createdAt time.Time

	err := r.db.QueryRowContext(ctx, `
		INSERT INTO chat_messages (channel_id, sender_id, body)
		VALUES ($1, $2, $3)
		RETURNING id, created_at
	`, channelID, senderID, body).Scan(&msgID, &createdAt)
	if err != nil {
		return nil, fmt.Errorf("create message: %w", err)
	}

	// Fetch with sender join for the full response
	msgs, err := r.getMessageByID(ctx, msgID)
	if err != nil {
		return nil, err
	}
	return msgs, nil
}

func (r *ChatRepository) getMessageByID(ctx context.Context, msgID int64) (*Message, error) {
	msg := &Message{}
	err := r.db.QueryRowContext(ctx, `
		SELECT m.id, m.channel_id, m.sender_id,
		       COALESCE(u.full_name, u.email) AS sender_name,
		       u.email                         AS sender_email,
		       COALESCE(u.profile_picture, '')  AS sender_avatar,
		       m.body, m.is_deleted, m.created_at
		FROM chat_messages m
		JOIN users u ON u.id = m.sender_id
		WHERE m.id = $1
	`, msgID).Scan(
		&msg.ID, &msg.ChannelID, &msg.SenderID,
		&msg.SenderName, &msg.SenderEmail, &msg.SenderAvatar,
		&msg.Body, &msg.IsDeleted, &msg.CreatedAt,
	)
	return msg, err
}

// SoftDeleteMessage marks a message as deleted.
// Only the sender or an admin can delete.
func (r *ChatRepository) SoftDeleteMessage(
	ctx context.Context,
	msgID, callerID int64,
	isAdmin bool,
) error {
	var query string
	var args []interface{}

	if isAdmin {
		query = `UPDATE chat_messages SET is_deleted = true WHERE id = $1`
		args = []interface{}{msgID}
	} else {
		query = `UPDATE chat_messages SET is_deleted = true WHERE id = $1 AND sender_id = $2`
		args = []interface{}{msgID, callerID}
	}

	res, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("message not found or permission denied")
	}
	return nil
}

// GetMessageChannelID returns the channel_id for a message (for access checks).
func (r *ChatRepository) GetMessageChannelID(ctx context.Context, msgID int64) (int64, error) {
	var channelID int64
	err := r.db.QueryRowContext(ctx,
		`SELECT channel_id FROM chat_messages WHERE id = $1`, msgID,
	).Scan(&channelID)
	if err == sql.ErrNoRows {
		return 0, fmt.Errorf("message not found")
	}
	return channelID, err
}

// ListAllChannels returns all channels for admin view (excludes DMs).
func (r *ChatRepository) ListAllChannels(ctx context.Context) ([]Channel, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, slug, name, description, is_private, is_dm, created_by, created_at
		FROM chat_channels
		WHERE is_dm = false
		ORDER BY created_at ASC
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var channels []Channel
	for rows.Next() {
		var ch Channel
		if err := rows.Scan(
			&ch.ID, &ch.Slug, &ch.Name, &ch.Description,
			&ch.IsPrivate, &ch.IsDM, &ch.CreatedBy, &ch.CreatedAt,
		); err != nil {
			return nil, err
		}
		channels = append(channels, ch)
	}
	return channels, rows.Err()
}

// GetDMParticipants returns a map of channelID -> User for the other participant in each specified DM channel.
func (r *ChatRepository) GetDMParticipants(ctx context.Context, channelIDs []int64, excludeUserID int64) (map[int64]User, error) {
	if len(channelIDs) == 0 {
		return map[int64]User{}, nil
	}

	// Build placeholders starting at $2 since $1 is excludeUserID
	placeholders := make([]string, len(channelIDs))
	args := make([]interface{}, len(channelIDs)+1)
	args[0] = excludeUserID
	for i, cid := range channelIDs {
		placeholders[i] = fmt.Sprintf("$%d", i+2)
		args[i+1] = cid
	}

	query := fmt.Sprintf(`
		SELECT ccu.channel_id, u.id, u.email, u.full_name, u.profile_picture
		FROM chat_channel_users ccu
		JOIN users u ON u.id = ccu.user_id
		WHERE ccu.channel_id IN (%s) AND ccu.user_id != $1
	`, strings.Join(placeholders, ","))

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := make(map[int64]User)
	for rows.Next() {
		var channelID int64
		var u User
		var pic sql.NullString
		if err := rows.Scan(&channelID, &u.ID, &u.Email, &u.FullName, &pic); err != nil {
			return nil, err
		}
		u.ProfilePicture = pic.String
		result[channelID] = u
	}
	return result, rows.Err()
}

// ── helpers ──────────────────────────────────────────────────────────────────

// buildRoleArgs builds a PostgreSQL IN clause and args slice.
// $1 is reserved for the channelID/userID; roles start at $2.
func buildRoleArgs(firstArg interface{}, roles []string) (string, []interface{}) {
	args := make([]interface{}, 0, len(roles)+1)
	args = append(args, firstArg)

	phs := make([]string, len(roles))
	for i, r := range roles {
		args = append(args, r)
		phs[i] = fmt.Sprintf("$%d", i+2)
	}
	return strings.Join(phs, ","), args
}

// SeedDefaultChannel checks if the 'general' channel exists. If not, it creates it using the first available user.
// Returns (true, nil) if seeded, (false, nil) if skipped, and (false, err) if failed.
func (r *ChatRepository) SeedDefaultChannel(ctx context.Context) (bool, error) {
	var count int
	err := r.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM chat_channels WHERE slug = 'general'`).Scan(&count)
	if err != nil {
		return false, err
	}
	if count > 0 {
		return false, nil // already seeded
	}

	var firstUserID int64
	err = r.db.QueryRowContext(ctx, `SELECT id FROM users ORDER BY id ASC LIMIT 1`).Scan(&firstUserID)
	if err == sql.ErrNoRows {
		return false, nil // no users synced yet
	}
	if err != nil {
		return false, err
	}

	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return false, err
	}
	defer func() { _ = tx.Rollback() }()

	var channelID int64
	err = tx.QueryRowContext(ctx, `
		INSERT INTO chat_channels (slug, name, description, is_private, is_dm, created_by)
		VALUES ('general', 'General', 'Club-wide discussion', false, false, $1)
		ON CONFLICT (slug) DO NOTHING
		RETURNING id
	`, firstUserID).Scan(&channelID)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}

	// Give all roles read+write access to general channel
	for _, role := range []string{"ADMIN", "TEACHER", "STUDENT"} {
		if _, err := tx.ExecContext(ctx, `
			INSERT INTO chat_channel_roles (channel_id, role_name, can_read, can_write)
			VALUES ($1, $2, true, true)
			ON CONFLICT DO NOTHING
		`, channelID, role); err != nil {
			return false, fmt.Errorf("seed role %s: %w", role, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return false, err
	}

	return true, nil
}
