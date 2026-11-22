package testutil

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
)

// Database installs real forward-only migrations into a unique, disposable database.
func Database(t *testing.T) *sql.DB {
	t.Helper()
	url := os.Getenv("LMS_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set LMS_TEST_DATABASE_URL to a disposable PostgreSQL database")
	}
	cfg, err := pgx.ParseConfig(url)
	if err != nil {
		t.Fatal(err)
	}
	admin := stdlib.OpenDB(*cfg)
	databaseName := "lms_safety_" + uuid.NewString()[:8]
	if _, err := admin.Exec(`CREATE DATABASE ` + databaseName); err != nil {
		t.Fatal(err)
	}
	cfg.Database = databaseName
	cfg.DefaultQueryExecMode = pgx.QueryExecModeSimpleProtocol
	db := stdlib.OpenDB(*cfg)
	db.SetMaxOpenConns(12)
	t.Cleanup(func() { db.Close(); admin.Exec(`DROP DATABASE ` + databaseName + ` WITH (FORCE)`); admin.Close() })
	_, file, _, _ := runtime.Caller(0)
	paths, err := filepath.Glob(filepath.Join(filepath.Dir(file), "../../migrations/releases/*/V*.sql"))
	if err != nil {
		t.Fatal(err)
	}
	sort.Slice(paths, func(i, j int) bool { return filepath.Base(paths[i]) < filepath.Base(paths[j]) })
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := db.ExecContext(context.Background(), string(raw)); err != nil {
			t.Fatalf("migration %s: %v", filepath.Base(path), err)
		}
	}
	return db
}
func SeedQuiz(t *testing.T, db *sql.DB) {
	t.Helper()
	_, err := db.Exec(`INSERT INTO users(id,email,full_name) VALUES(1,'owner@example.invalid','Owner'),(2,'student@example.invalid','Student'),(3,'other@example.invalid','Other');
 INSERT INTO courses(id,title,status,created_by,visibility,org_id) VALUES(1,'Course','PUBLISHED',1,'ORG_ONLY',(SELECT id FROM organizations WHERE slug='bdc'));
 INSERT INTO course_sections(id,course_id,title,order_index,is_published) VALUES(1,1,'Chapter',1,true);
 INSERT INTO section_content(id,section_id,type,title,order_index,is_published,file_path,created_by) VALUES(1,1,'QUIZ','Quiz',1,true,'document/private.pdf',1);
 INSERT INTO enrollments(course_id,student_id,status) VALUES(1,2,'ACCEPTED');
 INSERT INTO quizzes(id,content_id,title,is_published,auto_grade,max_attempts,total_points,show_results_immediately,created_by) VALUES(1,1,'Quiz',true,true,1,10,false,1);`)
	if err != nil {
		t.Fatal(err)
	}
}
