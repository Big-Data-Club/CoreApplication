package handler

import (
	"testing"
)

func TestToUTF8(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "Valid UTF-8",
			input:    "concepto-de-navegación",
			expected: "concepto-de-navegación",
		},
		{
			name:     "ISO-8859-1 ó (0xf3)",
			input:    "concepto-de-navegaci\xf3n",
			expected: "concepto-de-navegación",
		},
		{
			name:     "Plain ASCII",
			input:    "hello-world",
			expected: "hello-world",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := toUTF8(tt.input)
			if got != tt.expected {
				t.Errorf("toUTF8(%q) = %q; want %q", tt.input, got, tt.expected)
			}
		})
	}
}

func TestSanitizeFilePath(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		wantPath  string
		wantValid bool
	}{
		{
			name:      "Valid standard path",
			input:     "image/20260501160325_7be95c93_hello.jpg",
			wantPath:  "image/20260501160325_7be95c93_hello.jpg",
			wantValid: true,
		},
		{
			name:      "Path with UTF-8 URL encoding",
			input:     "image/20260501160325_7be95c93_concepto-de-navegaci%C3%B3n.jpg",
			wantPath:  "image/20260501160325_7be95c93_concepto-de-navegación.jpg",
			wantValid: true,
		},
		{
			name:      "Path with ISO-8859-1 URL encoding",
			input:     "image/20260501160325_7be95c93_concepto-de-navegaci%F3n.jpg",
			wantPath:  "image/20260501160325_7be95c93_concepto-de-navegación.jpg",
			wantValid: true,
		},
		{
			name:      "Path with space",
			input:     "image/hello world.jpg",
			wantPath:  "image/hello world.jpg",
			wantValid: true,
		},
		{
			name:      "Path with URL encoded space",
			input:     "image/hello%20world.jpg",
			wantPath:  "image/hello world.jpg",
			wantValid: true,
		},
		{
			name:      "Directory traversal warning",
			input:     "image/../../etc/passwd",
			wantPath:  "",
			wantValid: false,
		},
		{
			name:      "Absolute path with single leading slash (allowed for Gin)",
			input:     "/etc/passwd",
			wantPath:  "etc/passwd",
			wantValid: true,
		},
		{
			name:      "Absolute path with double leading slash",
			input:     "//etc/passwd",
			wantPath:  "",
			wantValid: false,
		},
		{
			name:      "Invalid character",
			input:     "image/hello#world.jpg", // # is not in isAllowedPathChar
			wantPath:  "",
			wantValid: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotPath, gotValid := sanitizeFilePath(tt.input)
			if gotValid != tt.wantValid {
				t.Fatalf("sanitizeFilePath(%q) got valid = %v; want %v", tt.input, gotValid, tt.wantValid)
			}
			if gotValid && gotPath != tt.wantPath {
				t.Errorf("sanitizeFilePath(%q) got path = %q; want %q", tt.input, gotPath, tt.wantPath)
			}
		})
	}
}
