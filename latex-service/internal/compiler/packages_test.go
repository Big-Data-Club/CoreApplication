package compiler

import (
	"testing"
)

func TestPackageRegistry_NewPackageRegistry_InitializesWithPackages(t *testing.T) {
	// Act
	reg := NewPackageRegistry()

	// Assert
	if reg == nil {
		t.Fatal("Expected PackageRegistry to be initialized, got nil")
	}

	pkgs := reg.List()
	if len(pkgs) == 0 {
		t.Error("Expected packages list to be non-empty")
	}
}

func TestPackageRegistry_Search_ReturnsCorrectResults(t *testing.T) {
	// Arrange
	reg := NewPackageRegistry()

	tests := []struct {
		name          string
		query         string
		expectedExist bool
	}{
		{
			name:          "exact match lowercase",
			query:         "amsmath",
			expectedExist: true,
		},
		{
			name:          "partial match mixed case",
			query:         "TikZ",
			expectedExist: true,
		},
		{
			name:          "no match",
			query:         "non-existent-package-name",
			expectedExist: false,
		},
		{
			name:          "empty query returns all",
			query:         "",
			expectedExist: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			results := reg.Search(tt.query)
			
			if tt.query == "" {
				if len(results) != len(reg.List()) {
					t.Errorf("Expected empty query to return all %d packages, got %d", len(reg.List()), len(results))
				}
				return
			}

			found := false
			for _, pkg := range results {
				if pkg.Name == tt.query || (tt.name == "partial match mixed case" && pkg.Name == "tikz") {
					found = true
					break
				}
			}

			if found != tt.expectedExist {
				t.Errorf("For query %q, expected found to be %t, got %t (results size: %d)", tt.query, tt.expectedExist, found, len(results))
			}
		})
	}
}
