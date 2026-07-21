package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
)

// UserRepository handles user sync from auth-service.
// Users are created/updated via the sync endpoint and looked up
// when building message responses.
type UserRepository struct {
	db *sql.DB
}

func NewUserRepository(db *sql.DB) *UserRepository {
	return &UserRepository{db: db}
}

type User struct {
	ID             int64
	Email          string
	FullName       string
	ProfilePicture string
}

// Upsert inserts or updates a user record from auth-service sync data.
func (r *UserRepository) Upsert(ctx context.Context, u User) error {
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO users (id, email, full_name, profile_picture, updated_at)
		VALUES ($1, $2, $3, $4, NOW())
		ON CONFLICT (id) DO UPDATE SET
			email           = EXCLUDED.email,
			full_name       = EXCLUDED.full_name,
			profile_picture = EXCLUDED.profile_picture,
			updated_at      = NOW()
	`, u.ID, u.Email, u.FullName, nullString(u.ProfilePicture))
	return err
}

// BulkUpsert upserts many users in a single query to minimize round-trips.
func (r *UserRepository) BulkUpsert(ctx context.Context, users []User) error {
	if len(users) == 0 {
		return nil
	}

	var sb strings.Builder
	sb.WriteString("INSERT INTO users (id, email, full_name, profile_picture, updated_at) VALUES ")

	args := make([]interface{}, 0, len(users)*4)
	for i, u := range users {
		if i > 0 {
			sb.WriteString(", ")
		}
		p1 := i*4 + 1
		p2 := i*4 + 2
		p3 := i*4 + 3
		p4 := i*4 + 4
		sb.WriteString(fmt.Sprintf("($%d, $%d, $%d, $%d, NOW())", p1, p2, p3, p4))
		args = append(args, u.ID, u.Email, u.FullName, nullString(u.ProfilePicture))
	}

	sb.WriteString(`
		ON CONFLICT (id) DO UPDATE SET
			email           = EXCLUDED.email,
			full_name       = EXCLUDED.full_name,
			profile_picture = EXCLUDED.profile_picture,
			updated_at      = NOW()
	`)

	_, err := r.db.ExecContext(ctx, sb.String(), args...)
	return err
}

// GetByID returns a user by primary key.
func (r *UserRepository) GetByID(ctx context.Context, id int64) (*User, error) {
	u := &User{}
	var pic sql.NullString
	err := r.db.QueryRowContext(ctx,
		`SELECT id, email, full_name, profile_picture FROM users WHERE id = $1`, id,
	).Scan(&u.ID, &u.Email, &u.FullName, &pic)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	u.ProfilePicture = pic.String
	return u, nil
}

// GetByIDs batch-fetches users by IDs. Returns a map[id]User.
func (r *UserRepository) GetByIDs(ctx context.Context, ids []int64) (map[int64]User, error) {
	if len(ids) == 0 {
		return map[int64]User{}, nil
	}

	// Build positional params: WHERE id IN ($1,$2,...)
	placeholders := make([]string, len(ids))
	args := make([]interface{}, len(ids))
	for i, id := range ids {
		placeholders[i] = fmt.Sprintf("$%d", i+1)
		args[i] = id
	}

	query := fmt.Sprintf(
		`SELECT id, email, full_name, profile_picture FROM users WHERE id IN (%s)`,
		strings.Join(placeholders, ","),
	)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := make(map[int64]User, len(ids))
	for rows.Next() {
		var u User
		var pic sql.NullString
		if err := rows.Scan(&u.ID, &u.Email, &u.FullName, &pic); err != nil {
			return nil, err
		}
		u.ProfilePicture = pic.String
		result[u.ID] = u
	}
	return result, rows.Err()
}

// EnsureGuestUser creates a minimal user record from JWT claims if the user
// hasn't been synced yet. This prevents FK violations on message insert.
func (r *UserRepository) EnsureGuestUser(ctx context.Context, id int64, email string) error {
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO users (id, email, full_name, updated_at)
		VALUES ($1, $2, $2, NOW())
		ON CONFLICT (id) DO NOTHING
	`, id, email)
	return err
}

// SearchUsers returns users matching a query (substring match on email or full_name).
// Excludes the current user from the results.
func (r *UserRepository) SearchUsers(ctx context.Context, query string, excludeUserID int64, limit int) ([]User, error) {
	if query == "" {
		return []User{}, nil
	}
	likePattern := "%" + strings.ToLower(query) + "%"
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, email, full_name, profile_picture
		FROM users
		WHERE id != $1 AND (LOWER(email) LIKE $2 OR LOWER(full_name) LIKE $2)
		ORDER BY full_name ASC
		LIMIT $3
	`, excludeUserID, likePattern, limit)
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

// ── helpers ──────────────────────────────────────────────────────────────────

func nullString(s string) sql.NullString {
	if s == "" {
		return sql.NullString{}
	}
	return sql.NullString{String: s, Valid: true}
}
