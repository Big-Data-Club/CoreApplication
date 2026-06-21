package compiler

import (
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"time"
)

// SandboxResult contains the result of a sandboxed command execution
type SandboxResult struct {
	Success      bool
	LogOutput    string
	ErrorMessage string
	Duration     time.Duration
}

// RunCompiler runs pdflatex, xelatex, or lualatex in a sandboxed way
func RunCompiler(ctx context.Context, compilerPath string, workDir string, mainFile string, timeout time.Duration) (*SandboxResult, error) {
	// Setup context with timeout
	runCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Ensure mainFile is relative to workDir and doesn't escape
	cleanMainFile := filepath.Base(mainFile)

	// Build directory inside workDir to hold output files
	outputDirName := "output"

	start := time.Now()

	// pdflatex / xelatex / lualatex arguments:
	// -interaction=nonstopmode (do not halt on error, output logs)
	// -no-shell-escape (disable \write18 command execution)
	// -output-directory=outputDir (keep workspace clean)
	cmd := exec.CommandContext(runCtx, compilerPath,
		"-interaction=nonstopmode",
		"-no-shell-escape",
		"-output-directory="+outputDirName,
		cleanMainFile,
	)

	cmd.Dir = workDir

	// Capture stdout and stderr
	// Actually, we can capture combined output
	outputBytes, err := cmd.CombinedOutput()
	duration := time.Since(start)

	logOutput := string(outputBytes)

	// Check if context timeout occurred
	if runCtx.Err() == context.DeadlineExceeded {
		return &SandboxResult{
			Success:      false,
			LogOutput:    logOutput,
			ErrorMessage: "Compilation timed out after " + timeout.String(),
			Duration:     duration,
		}, nil
	}

	if err != nil {
		return &SandboxResult{
			Success:      false,
			LogOutput:    logOutput,
			ErrorMessage: fmt.Sprintf("Compiler exited with error: %v", err),
			Duration:     duration,
		}, nil
	}

	return &SandboxResult{
		Success:  true,
		LogOutput: logOutput,
		Duration: duration,
	}, nil
}
