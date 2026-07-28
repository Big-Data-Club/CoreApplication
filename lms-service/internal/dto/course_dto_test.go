package dto

import (
	"testing"

	"github.com/go-playground/validator/v10"
)

func TestCreateContentRequestAllowsFirstOrderIndex(t *testing.T) {
	validate := validator.New()
	validate.SetTagName("binding")
	req := CreateContentRequest{
		Type:       "DOCUMENT",
		Title:      "First file",
		OrderIndex: 0,
	}

	if err := validate.Struct(req); err != nil {
		t.Fatalf("order_index=0 must be valid for the first content item: %v", err)
	}
}

func TestCreateContentRequestRejectsNegativeOrderIndex(t *testing.T) {
	validate := validator.New()
	validate.SetTagName("binding")
	req := CreateContentRequest{
		Type:       "DOCUMENT",
		Title:      "Invalid order",
		OrderIndex: -1,
	}

	if err := validate.Struct(req); err == nil {
		t.Fatal("negative order_index must be rejected")
	}
}
