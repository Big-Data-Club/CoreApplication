package service

import (
	"context"
	"errors"
	"testing"
)

type fileStoreFixture struct {
	read, manage bool
	err          error
}

func (f fileStoreFixture) Register(context.Context, string, int64, int64, bool) error { return nil }
func (f fileStoreFixture) Forget(context.Context, string) error                       { return nil }
func (f fileStoreFixture) Access(context.Context, string, int64) (bool, bool, error) {
	return f.read, f.manage, f.err
}
func TestFilePolicyDistinguishesReadFromDelete(t *testing.T) {
	for _, tc := range []struct {
		name, role               string
		store                    fileStoreFixture
		internal, write, allowed bool
	}{
		{name: "reader cannot delete", store: fileStoreFixture{read: true}, write: true},
		{name: "owner can delete", store: fileStoreFixture{manage: true}, write: true, allowed: true},
		{name: "reader", store: fileStoreFixture{read: true}, allowed: true},
		{name: "outage denies", store: fileStoreFixture{err: errors.New("database offline")}},
		{name: "internal", internal: true, allowed: true},
		{name: "admin", role: "ADMIN", write: true, allowed: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := NewFileAccessService(tc.store).Authorize(context.Background(), "document/a.pdf", 41, tc.role, tc.internal, tc.write)
			if (err == nil) != tc.allowed {
				t.Fatalf("err=%v allowed=%v", err, tc.allowed)
			}
		})
	}
}
