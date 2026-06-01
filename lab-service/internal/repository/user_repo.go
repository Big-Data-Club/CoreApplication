package repository

import (
	"context"
	"database/sql"
	"time"
)

type UserRepository struct{ db *sql.DB }

func NewUserRepository(db *sql.DB) *UserRepository {
	return &UserRepository{db: db}
}

type UserSyncRequest struct {
	ID       int64    `json:"id"`
	Email    string   `json:"email"`
	FullName string   `json:"fullName"`
	Roles    []string `json:"roles"`
	IsActive bool     `json:"isActive"`
}

func (r *UserRepository) SyncUser(ctx context.Context, req *UserSyncRequest) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO users (id, email, full_name, roles, is_active, synced_at)
		VALUES ($1, $2, $3, $4, $5, $6)
		ON CONFLICT (id) DO UPDATE SET
			email = EXCLUDED.email,
			full_name = EXCLUDED.full_name,
			roles = EXCLUDED.roles,
			is_active = EXCLUDED.is_active,
			synced_at = EXCLUDED.synced_at`,
		req.ID, req.Email, req.FullName, req.Roles, req.IsActive, time.Now())
	return err
}

func (r *UserRepository) BulkSyncUsers(ctx context.Context, users []UserSyncRequest) error {
	for _, u := range users {
		if err := r.SyncUser(ctx, &u); err != nil {
			return err
		}
	}
	return nil
}
