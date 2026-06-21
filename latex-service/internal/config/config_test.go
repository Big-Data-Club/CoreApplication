package config

import (
	"os"
	"testing"
)

func TestLoad_WithValidEnvVars_LoadsConfigSuccessfully(t *testing.T) {
	// Arrange
	os.Setenv("LATEX_PORT", "8089")
	os.Setenv("LATEX_DB_HOST", "test-db-host")
	os.Setenv("JWT_SECRET", "test_secret_key_that_is_at_least_32_chars_long_for_security")

	// Act
	cfg, err := Load()

	// Assert
	if err != nil {
		t.Fatalf("Expected no error loading config, got %v", err)
	}
	if cfg.App.Port != "8089" {
		t.Errorf("Expected port 8089, got %s", cfg.App.Port)
	}
	if cfg.Database.Host != "test-db-host" {
		t.Errorf("Expected database host test-db-host, got %s", cfg.Database.Host)
	}
}
