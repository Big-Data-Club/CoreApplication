package dto

import (
	"encoding/json"
	"github.com/go-playground/validator/v10"
	"testing"
)

func TestQuizFocusSummaryBounds(t *testing.T) {
	validate := validator.New()
	validate.SetTagName("binding")
	for _, summary := range []QuizFocusSummary{{0, 0}, {100000, 31536000}} {
		if err := validate.Struct(summary); err != nil {
			t.Fatal(err)
		}
	}
	for _, summary := range []QuizFocusSummary{{-1, 0}, {0, -1}, {100001, 0}, {0, 31536001}} {
		if err := validate.Struct(summary); err == nil {
			t.Fatalf("accepted invalid summary: %+v", summary)
		}
	}
	var request SubmitQuizRequest
	if err := json.Unmarshal([]byte(`{}`), &request); err != nil || request.FocusSummary != nil {
		t.Fatal("legacy empty submission must remain valid")
	}
}
