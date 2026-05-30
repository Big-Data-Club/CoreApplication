package service

import (
	"testing"
)

func TestEmailParserRegex_ExtractEmails_WithVariousSeparators(t *testing.T) {
	// Arrange
	input := `
		test1@example.com,test2@example.com;test3@example.com
		test4@example.com   test5@example.com
		Name <test6@example.com> "Other" test7@example.com
	`
	expected := []string{
		"test1@example.com",
		"test2@example.com",
		"test3@example.com",
		"test4@example.com",
		"test5@example.com",
		"test6@example.com",
		"test7@example.com",
	}

	// Act
	matches := emailParserRegex.FindAllString(input, -1)

	// Assert
	if len(matches) != len(expected) {
		t.Fatalf("expected %d matches, got %d", len(expected), len(matches))
	}

	for i, match := range matches {
		if match != expected[i] {
			t.Errorf("at index %d: expected %s, got %s", i, expected[i], match)
		}
	}
}
