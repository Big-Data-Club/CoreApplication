package dto

import (
	"strings"
	"testing"

	"github.com/gin-gonic/gin/binding"
)

func TestQuestionUpdatePreservesOmittedAndExplicitValues(t *testing.T) {
	for _, tc := range []struct {
		body            string
		lists, required bool
	}{
		{`{"question_text":"updated"}`, false, false},
		{`{"is_required":false,"answer_options":[],"correct_answers":[]}`, true, true},
		{`{"is_required":true,"answer_options":[{"id":7,"option_text":"A","order_index":0,"is_correct":true}],"correct_answers":[]}`, true, true},
	} {
		var req UpdateQuestionRequest
		if err := binding.JSON.BindBody([]byte(tc.body), &req); err != nil {
			t.Fatal(err)
		}
		if (req.AnswerOptions != nil) != tc.lists || (req.CorrectAnswers != nil) != tc.lists {
			t.Fatalf("list presence lost for %s", tc.body)
		}
		if (req.IsRequired != nil) != tc.required {
			t.Fatalf("required flag presence lost for %s", tc.body)
		}
		if strings.Contains(tc.body, `"is_required":false`) && *req.IsRequired {
			t.Fatal("explicit false lost")
		}
		if req.OrderIndex != nil {
			t.Fatal("content update must not supply a new position")
		}
	}
}

func TestQuestionUpdateRejectsInvalidOptions(t *testing.T) {
	for _, body := range []string{
		`{"answer_options":[{"option_text":"","order_index":0}]}`,
		`{"answer_options":[{"option_text":"A","order_index":-1}]}`,
		`{"answer_options":[{"id":-1,"option_text":"A","order_index":0}]}`,
	} {
		var req UpdateQuestionRequest
		if err := binding.JSON.BindBody([]byte(body), &req); err == nil {
			t.Fatalf("accepted invalid option: %s", body)
		}
	}
}
