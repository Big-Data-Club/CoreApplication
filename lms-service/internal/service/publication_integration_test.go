package service

import (
	"context"
	"testing"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/migrations"
	"example/hello/pkg/database"
)

func TestPublicationNormalizesClientFlagsAndNotifiesEnrolledStudents(t *testing.T) {
	quizzes, db := quizFixture(t)
	courses := NewCourseService(repository.NewCourseRepository(db), repository.NewUserRepository(db), repository.NewEnrollmentRepository(db), repository.NewOrganizationRepository(db), nil, nil)
	ctx := context.Background()
	for _, table := range []string{"course_sections", "section_content", "quizzes"} {
		if _, err := db.Exec(`SELECT setval(pg_get_serial_sequence('` + table + `','id'),(SELECT max(id) FROM ` + table + `))`); err != nil {
			t.Fatal(err)
		}
	}
	section, err := courses.CreateSection(ctx, 1, &dto.CreateSectionRequest{Title: "New chapter", OrderIndex: 2}, 1, "TEACHER")
	if err != nil || !section.IsPublished {
		t.Fatalf("section: %+v %v", section, err)
	}
	content, err := courses.CreateContent(ctx, section.ID, &dto.CreateContentRequest{Title: "New quiz", Type: "QUIZ", OrderIndex: 1}, 1, "TEACHER")
	if err != nil || !content.IsPublished {
		t.Fatalf("content: %+v %v", content, err)
	}
	quiz, err := quizzes.CreateQuiz(ctx, &dto.CreateQuizRequest{ContentID: content.ID, Title: "New quiz", TotalPoints: 10}, 1, "TEACHER")
	if err != nil || !quiz.IsPublished {
		t.Fatalf("quiz: %+v %v", quiz, err)
	}
	disabled := false
	if err := courses.UpdateSection(ctx, section.ID, &dto.UpdateSectionRequest{IsPublished: &disabled}, 1, "TEACHER"); err != nil {
		t.Fatal(err)
	}
	if err := courses.UpdateContent(ctx, content.ID, &dto.UpdateContentRequest{IsPublished: &disabled}, 1, "TEACHER"); err != nil {
		t.Fatal(err)
	}
	updated, err := quizzes.UpdateQuiz(ctx, quiz.ID, &dto.UpdateQuizRequest{IsPublished: &disabled}, 1, "TEACHER")
	if err != nil || !updated.IsPublished {
		t.Fatalf("quiz update: %+v %v", updated, err)
	}

	for _, table := range []string{"course_sections", "section_content", "quizzes"} {
		for _, value := range []interface{}{nil, false, true} {
			var published bool
			if err := db.QueryRow(`UPDATE `+table+` SET is_published=$1 WHERE id=1 RETURNING is_published`, value).Scan(&published); err != nil || !published {
				t.Fatalf("%s value=%v: %v", table, value, err)
			}
		}
	}
	for i, value := range []interface{}{nil, false, true} {
		id := 2000 + i
		var published bool
		if err := db.QueryRow(`INSERT INTO course_sections(id,course_id,title,order_index,is_published) VALUES($1,1,'Direct section',$1,$2) RETURNING is_published`, id, value).Scan(&published); err != nil || !published {
			t.Fatalf("direct section insert: %v", err)
		}
		if err := db.QueryRow(`INSERT INTO section_content(id,section_id,title,type,order_index,created_by,is_published) VALUES($1,$1,'Direct lesson','QUIZ',1,1,$2) RETURNING is_published`, id, value).Scan(&published); err != nil || !published {
			t.Fatalf("direct content insert: %v", err)
		}
		if err := db.QueryRow(`INSERT INTO quizzes(id,content_id,title,created_by,is_published) VALUES($1,$1,'Direct quiz',1,$2) RETURNING is_published`, id, value).Scan(&published); err != nil || !published {
			t.Fatalf("direct quiz insert: %v", err)
		}
	}
	var before, after int
	if err := db.QueryRow(`SELECT count(*) FROM learning_notification_events WHERE content_id=$1 AND kind='content_updated'`, content.ID).Scan(&before); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`UPDATE quizzes SET title='Quiz revised' WHERE id=$1`, quiz.ID); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM learning_notification_events WHERE content_id=$1 AND kind='content_updated'`, content.ID).Scan(&after); err != nil || after != before+1 {
		t.Fatalf("quiz revision event: before=%d after=%d err=%v", before, after, err)
	}
	if _, err := db.Exec(`UPDATE quizzes SET total_points=20 WHERE id=$1`, quiz.ID); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM learning_notification_events WHERE content_id=$1 AND kind='content_updated'`, content.ID).Scan(&before); err != nil || before != after {
		t.Fatalf("score bookkeeping must not notify: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO organization_members(org_id,user_id) SELECT org_id,2 FROM courses WHERE id=1 ON CONFLICT DO NOTHING`); err != nil {
		t.Fatal(err)
	}
	notices := NewNotificationService(db, nil)
	feed, err := notices.Feed(ctx, 2)
	if err != nil || len(feed.Alerts) == 0 {
		t.Fatalf("enrolled feed: %+v %v", feed, err)
	}
	outsider, err := notices.Feed(ctx, 3)
	if err != nil || len(outsider.Alerts) != 0 {
		t.Fatalf("outside course feed: %+v %v", outsider, err)
	}
}

func TestPublicationMigrationBackfillsLegacyNullsAndStartupIsIdempotent(t *testing.T) {
	_, db := quizFixture(t)
	for _, table := range []string{"course_sections", "section_content", "quizzes"} {
		if _, err := db.Exec(`ALTER TABLE ` + table + ` DISABLE TRIGGER enforce_learning_publication; ALTER TABLE ` + table + ` ALTER COLUMN is_published DROP NOT NULL; UPDATE ` + table + ` SET is_published=NULL`); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := db.Exec(migrations.AlwaysPublishLearningResources); err != nil {
		t.Fatal(err)
	}
	for _, table := range []string{"course_sections", "section_content", "quizzes"} {
		var remaining int
		if err := db.QueryRow(`SELECT count(*) FROM ` + table + ` WHERE is_published IS DISTINCT FROM true`).Scan(&remaining); err != nil || remaining != 0 {
			t.Fatalf("%s backfill: %d %v", table, remaining, err)
		}
	}
	var before, after int
	if err := db.QueryRow(`SELECT count(*) FROM learning_notification_events`).Scan(&before); err != nil {
		t.Fatal(err)
	}
	if err := database.EnsureLearningNotificationSchema(context.Background(), db); err != nil {
		t.Fatal(err)
	}
	if err := database.EnsureLearningNotificationSchema(context.Background(), db); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM learning_notification_events`).Scan(&after); err != nil || before != after {
		t.Fatalf("startup replayed notifications: %d %d %v", before, after, err)
	}
}
