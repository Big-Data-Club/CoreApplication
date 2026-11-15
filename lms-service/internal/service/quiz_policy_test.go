package service

import (
	"context"
	"errors"
	"testing"
)

type accessFixture struct {
	manager, enrolled bool
	err               error
}

func (f accessFixture) QuizAccess(context.Context, int64, int64) (bool, bool, error) {
	return f.manager, f.enrolled, f.err
}
func TestQuizPolicyUsesResourceScope(t *testing.T) {
	for _, tc := range []struct {
		name, role      string
		fixture         accessFixture
		allowed, manage bool
	}{
		{"unrelated teacher", "TEACHER", accessFixture{}, false, false},
		{"unrelated dynamic role", "MENTOR", accessFixture{}, false, false},
		{"enrolled student", "STUDENT", accessFixture{enrolled: true}, true, false},
		{"co teacher", "TEACHER", accessFixture{manager: true}, true, true},
		{"admin", "ADMIN", accessFixture{}, true, true},
		{"db failure", "ADMIN", accessFixture{err: errors.New("db failure")}, false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			manager, err := (QuizPolicy{tc.fixture}).Check(context.Background(), 7, 41, tc.role)
			if (err == nil) != tc.allowed || manager != tc.manage {
				t.Fatalf("manager=%v err=%v", manager, err)
			}
		})
	}
}
