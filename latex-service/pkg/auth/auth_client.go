package auth

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
)

// UserInfo represents the user information returned by the auth service
type UserInfo struct {
	ID       int64  `json:"id"`
	Email    string `json:"email"`
	FullName string `json:"fullName"`
}

// AuthClient is an HTTP client for the auth-and-management-service
type AuthClient struct {
	baseURL    string
	httpClient *http.Client
}

// NewAuthClient creates a new AuthClient targeting the given base URL
func NewAuthClient(baseURL string) *AuthClient {
	return &AuthClient{
		baseURL:    baseURL,
		httpClient: &http.Client{},
	}
}

// LookupUserByEmail searches for a user by email in the auth service.
// Calls GET {baseURL}/api/users/search?q={email}
func (c *AuthClient) LookupUserByEmail(ctx context.Context, email string) (*UserInfo, error) {
	reqURL := fmt.Sprintf("%s/api/users/search?q=%s", c.baseURL, url.QueryEscape(email))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create auth request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("auth service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("user with email %q not found", email)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("auth service returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read auth response: %w", err)
	}

	// Auth service returns: {"data": [{...}]} or {"data": {...}}
	var wrapper struct {
		Data json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(body, &wrapper); err != nil {
		return nil, fmt.Errorf("failed to parse auth response: %w", err)
	}

	// Try array first, then single object
	var users []UserInfo
	if err := json.Unmarshal(wrapper.Data, &users); err == nil {
		for _, u := range users {
			if u.Email == email {
				return &u, nil
			}
		}
		if len(users) > 0 {
			return &users[0], nil
		}
		return nil, fmt.Errorf("user with email %q not found", email)
	}

	// Try single object
	var user UserInfo
	if err := json.Unmarshal(wrapper.Data, &user); err != nil {
		return nil, fmt.Errorf("failed to parse user data: %w", err)
	}
	if user.ID == 0 {
		return nil, fmt.Errorf("user with email %q not found", email)
	}
	return &user, nil
}
