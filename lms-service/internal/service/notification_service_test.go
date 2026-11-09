package service

import (
	"strings"
	"testing"
)

func TestNotificationTargetsAndHumanNames(t *testing.T) {
	for _, tc := range []struct {
		kind     string
		count    int64
		enrolled bool
		href     string
	}{
		{"course_published", 1, false, "/lms/student/discover/42"},
		{"course_published", 1, true, "/lms/student/courses/42/learn"},
		{"content_added", 1, true, "/lms/student/courses/42/learn?contentId=9"},
		{"content_added", 5, true, "/lms/student/courses/42/learn?sectionId=7"},
		{"content_updated", 1, true, "/lms/student/courses/42/learn?contentId=9"},
		{"content_removed", 1, true, "/lms/student/courses/42/learn?sectionId=7"},
		{"section_removed", 1, true, "/lms/student/courses/42/learn"},
	} {
		t.Run(tc.kind+tc.href, func(t *testing.T) {
			n := LearningNotice{Type: tc.kind, CourseID: 42, SectionID: 7, ContentID: 9, CourseTitle: "Python", EntityTitle: "Vòng lặp"}
			formatLearningNotice(&n, tc.count, "Chương hai", tc.enrolled)
			if n.Href != tc.href {
				t.Fatalf("wrong target: %s", n.Href)
			}
			if n.Category != "learning" || !strings.Contains(n.Message, "Python") || strings.Contains(n.Message, "Course ID") {
				t.Fatalf("invalid display: %+v", n)
			}
		})
	}
}

func TestNotificationReadKeyValidation(t *testing.T) {
	for _, key := range []string{"learning:12", "deadline:14:1800000000", "suggestion:concept_struggle:42:9:2900", "suggestion:inactivity:42::2900"} {
		if !ValidNoticeKeys([]string{key}) {
			t.Fatal(key)
		}
	}
	for _, keys := range [][]string{nil, {"https://example.test"}, {"learning:1;DROP TABLE users"}, make([]string, 51)} {
		if ValidNoticeKeys(keys) {
			t.Fatalf("accepted invalid keys: %v", keys)
		}
	}
}

func TestNotificationRevisionRefreshesAlreadyOpenLesson(t *testing.T) {
	n := LearningNotice{ID: "learning:13", Type: "content_updated", CourseID: 42, SectionID: 7, ContentID: 9, CourseTitle: "Python", EntityTitle: "Vòng lặp"}
	formatLearningNotice(&n, 1, "Chương hai", true)
	if n.Href != "/lms/student/courses/42/learn?contentId=9&notice=learning%3A13" {
		t.Fatalf("missing revision: %s", n.Href)
	}
}
