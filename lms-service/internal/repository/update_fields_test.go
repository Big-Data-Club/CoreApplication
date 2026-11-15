package repository

import (
	"context"
	"errors"
	"testing"

	"example/hello/internal/testutil"
)

func TestDynamicUpdateRejectsIdentifiersBeforeDatabase(t *testing.T) {
	if err := NewCourseRepository(nil).Update(context.Background(), 1, map[string]interface{}{"title = 'owned'; DELETE FROM users; --": "x"}); !errors.Is(err, ErrInvalidUpdateField) {
		t.Fatalf("unsafe identifier reached persistence: %v", err)
	}
	if err := NewForumRepository(nil).UpdatePost(context.Background(), 1, map[string]interface{}{"user_id": 99}); !errors.Is(err, ErrInvalidUpdateField) {
		t.Fatalf("owner field was editable: %v", err)
	}
}
func TestUpdateKeepsSQLTextAsLiteralValue(t *testing.T) {
	db := testutil.Database(t)
	testutil.SeedQuiz(t, db)
	value := "Fixture'; DELETE FROM users; --"
	if err := NewCourseRepository(db).Update(context.Background(), 1, map[string]interface{}{"title": value}); err != nil {
		t.Fatal(err)
	}
	var actual string
	var users int
	if err := db.QueryRow(`SELECT title FROM courses WHERE id=1`).Scan(&actual); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM users`).Scan(&users); err != nil {
		t.Fatal(err)
	}
	if actual != value || users != 3 {
		t.Fatal("SQL-looking value was not preserved literally")
	}
}
