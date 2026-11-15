package repository

import (
	"errors"
	"slices"
)

var ErrInvalidUpdateField = errors.New("unsupported update field")

// SQL bind parameters protect values, not identifiers. Keep the identifier
// allowlist inside persistence even when today's HTTP DTO already restricts keys.
func validateUpdateFields(updates map[string]interface{}, allowed ...string) error {
	for field := range updates {
		if !slices.Contains(allowed, field) {
			return ErrInvalidUpdateField
		}
	}
	return nil
}
