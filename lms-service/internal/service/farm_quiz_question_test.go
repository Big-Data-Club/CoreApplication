package service

import (
	"database/sql"
	"encoding/json"
	"strings"
	"testing"
)

func TestFarmQuizPreservesImagesInAnswerOrder(t *testing.T) {
	options := []byte(`[
	 {"option_text":"Wrong","order_index":2,"is_correct":false},
	 {"option_text":"","order_index":1,"is_correct":true,"image":{"url":"https://example.com/bird.png","alt_text":"Bird","file_path":"private-storage-path"}}
	]`)
	settings := []byte(`{"images":[{"url":"https://example.com/tree.png","position":"below_question","caption":"Decision tree","display_width":"500px"}],"correct_answers":["must not be forwarded"]}`)
	q := farmQuizQuestion(7, 9, sql.NullInt64{Int64: 55, Valid: true}, "**Choose** $P(B)$", "Explanation", options, settings)
	if q == nil || q.Answer != "0" || len(q.Images) != 1 || q.Images[0].Position != "below_question" || q.NodeID == nil || *q.NodeID != 55 {
		t.Fatalf("question metadata lost: %+v", q)
	}
	if len(q.OptionImages) != 2 || q.OptionImages[0] == nil || q.OptionImages[0].AltText != "Bird" || q.OptionImages[1] != nil || q.Options[0] != "" {
		t.Fatalf("option image must follow sorted option, including image-only options: %+v", q)
	}
	raw, _ := json.Marshal(q)
	for _, private := range []string{"private-storage-path", "correct_answers", "is_correct"} {
		if strings.Contains(string(raw), private) {
			t.Fatalf("unapproved settings forwarded: %s", raw)
		}
	}
}

func TestFarmQuizLegacyTextAndInvalidAnswerKeys(t *testing.T) {
	q := farmQuizQuestion(1, 9, sql.NullInt64{}, "Question", "", []byte(`[{"option_text":"A","is_correct":true},{"option_text":"B"}]`), nil)
	if q == nil || q.Answer != "0" || q.OptionImages != nil || len(q.Images) != 0 {
		t.Fatalf("legacy question changed: %+v", q)
	}
	for _, raw := range []string{`invalid`, `[{"option_text":"A"},{"option_text":"B"}]`, `[{"is_correct":true},{"is_correct":true}]`} {
		if farmQuizQuestion(1, 9, sql.NullInt64{}, "Question", "", []byte(raw), nil) != nil {
			t.Fatalf("invalid answer key accepted: %s", raw)
		}
	}
}
