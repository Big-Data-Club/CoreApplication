package compiler

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

// buildSleeperBinary compiles a simple Go program that sleeps for 10 seconds.
func buildSleeperBinary(t *testing.T, tempDir string) string {
	srcPath := filepath.Join(tempDir, "sleeper.go")
	binPath := filepath.Join(tempDir, "sleeper")
	if runtime.GOOS == "windows" {
		binPath += ".exe"
	}

	src := []byte(`package main
import "time"
func main() {
	time.Sleep(10 * time.Second)
}
`)
	if err := os.WriteFile(srcPath, src, 0644); err != nil {
		t.Fatalf("Failed to write sleeper src: %v", err)
	}

	cmd := exec.Command("go", "build", "-o", binPath, srcPath)
	if err := cmd.Run(); err != nil {
		t.Fatalf("Failed to compile sleeper: %v", err)
	}

	return binPath
}

// buildQuickSuccessBinary compiles a simple Go program that exits immediately with status 0.
func buildQuickSuccessBinary(t *testing.T, tempDir string) string {
	srcPath := filepath.Join(tempDir, "success.go")
	binPath := filepath.Join(tempDir, "success")
	if runtime.GOOS == "windows" {
		binPath += ".exe"
	}

	src := []byte(`package main
import "fmt"
func main() {
	fmt.Println("Mock compiler run succeeded")
}
`)
	if err := os.WriteFile(srcPath, src, 0644); err != nil {
		t.Fatalf("Failed to write success src: %v", err)
	}

	cmd := exec.Command("go", "build", "-o", binPath, srcPath)
	if err := cmd.Run(); err != nil {
		t.Fatalf("Failed to compile success binary: %v", err)
	}

	return binPath
}

func TestRunCompiler_WithNonExistentExecutable_ReturnsError(t *testing.T) {
	// Arrange
	ctx := context.Background()
	tempDir, err := os.MkdirTemp("", "latex-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	// Act
	result, err := RunCompiler(ctx, "nonexistent-latex-compiler-xyz", tempDir, "main.tex", 5*time.Second)

	// Assert
	if err != nil {
		t.Fatalf("Expected no error from RunCompiler function wrap, but got: %v", err)
	}
	if result.Success {
		t.Error("Expected success to be false for nonexistent executable")
	}
	if !strings.Contains(result.ErrorMessage, "executable file not found") && !strings.Contains(result.ErrorMessage, "file does not exist") {
		t.Errorf("Expected error message to mention file not found, got: %s", result.ErrorMessage)
	}
}

func TestRunCompiler_WithTimeout_CancelsProcess(t *testing.T) {
	// Arrange
	ctx := context.Background()
	tempDir, err := os.MkdirTemp("", "latex-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	sleeperBin := buildSleeperBinary(t, tempDir)

	// Act
	// Set a very short timeout (100ms) so it will trigger the timeout path on the 10s sleeper
	result, err := RunCompiler(ctx, sleeperBin, tempDir, "main.tex", 100*time.Millisecond)

	// Assert
	if err != nil {
		t.Fatalf("Expected no error from RunCompiler wrapper, got: %v", err)
	}
	if result.Success {
		t.Error("Expected success to be false due to timeout")
	}
	if !strings.Contains(result.ErrorMessage, "timed out") {
		t.Errorf("Expected error message to contain 'timed out', got: %s", result.ErrorMessage)
	}
}

func TestRunCompiler_CreatesOutputDirName(t *testing.T) {
	// Arrange
	ctx := context.Background()
	tempDir, err := os.MkdirTemp("", "latex-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	successBin := buildQuickSuccessBinary(t, tempDir)

	// Create output dir if needed (since the cmd expects output dir to be in working directory)
	err = os.MkdirAll(filepath.Join(tempDir, "output"), 0755)
	if err != nil {
		t.Fatalf("Failed to create output dir: %v", err)
	}

	// Act
	result, err := RunCompiler(ctx, successBin, tempDir, "main.tex", 5*time.Second)

	// Assert
	if err != nil {
		t.Fatalf("Expected no error, got %v", err)
	}
	if !result.Success {
		t.Errorf("Expected success to be true, got false. Error: %s", result.ErrorMessage)
	}
	if !strings.Contains(result.LogOutput, "Mock compiler run succeeded") {
		t.Errorf("Expected log output to contain mock success output, got: %s", result.LogOutput)
	}
}
