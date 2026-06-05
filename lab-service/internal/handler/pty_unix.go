//go:build !windows

package handler

import (
	"encoding/json"
	"log"
	"os"
	"os/exec"
	"sync"
	"syscall"

	"github.com/creack/pty"
	"github.com/gorilla/websocket"
)

func startShellPTY(cmd *exec.Cmd, ws *websocket.Conn) error {
	log.Printf("[TerminalWS] Starting shell PTY: %s %v in dir: %s", cmd.Path, cmd.Args, cmd.Dir)

	// pty.Start internally calls Setsid + Setctty.
	// We must NOT set Setpgid=true here because combining Setpgid with
	// Setsid (which pty.Start sets) causes EINVAL on Linux.
	// Leave SysProcAttr nil so pty.Start can configure it correctly.
	cmd.SysProcAttr = nil

	f, err := pty.Start(cmd)
	if err != nil {
		log.Printf("[TerminalWS] pty.Start failed: %v, attempting manual PTY fallback", err)

		// Fallback: Open PTY pair manually, use Setsid only (no Setctty, no Setpgid)
		var tty *os.File
		f, tty, err = pty.Open()
		if err != nil {
			log.Printf("[TerminalWS] pty.Open failed: %v", err)
			return err
		}

		cmd.Stdin = tty
		cmd.Stdout = tty
		cmd.Stderr = tty
		cmd.SysProcAttr = &syscall.SysProcAttr{
			Setsid: true,
		}

		if err = cmd.Start(); err != nil {
			tty.Close()
			f.Close()
			log.Printf("[TerminalWS] manual PTY cmd.Start failed: %v", err)
			return err
		}
		defer tty.Close()
	}
	defer f.Close()

	// Set an initial reasonable terminal size (80x24 is standard)
	_ = pty.Setsize(f, &pty.Winsize{Rows: 24, Cols: 80})

	var once sync.Once
	killProcess := func() {
		once.Do(func() {
			if cmd.Process != nil {
				// Try to kill the entire process group (negative PID)
				// This works when Setsid was used (the shell became session leader)
				pgid, err := syscall.Getpgid(cmd.Process.Pid)
				if err == nil && pgid > 0 {
					_ = syscall.Kill(-pgid, syscall.SIGKILL)
				} else {
					_ = cmd.Process.Kill()
				}
			}
		})
	}
	defer killProcess()

	// PTY → WebSocket: read output from the shell and forward to the browser
	go func() {
		buf := make([]byte, 4096)
		for {
			n, err := f.Read(buf)
			if n > 0 {
				if writeErr := ws.WriteMessage(websocket.BinaryMessage, buf[:n]); writeErr != nil {
					break
				}
			}
			if err != nil {
				break
			}
		}
		_ = ws.Close()
	}()

	// WebSocket → PTY: read input from the browser and write to the shell
	for {
		mt, message, err := ws.ReadMessage()
		if err != nil {
			break
		}

		if mt == websocket.TextMessage {
			// Try to parse as JSON protocol message
			var msg wsMessage
			if json.Unmarshal(message, &msg) == nil {
				switch msg.Type {
				case "input":
					if _, err := f.Write([]byte(msg.Data)); err != nil {
						goto done
					}
				case "resize":
					if msg.Cols > 0 && msg.Rows > 0 {
						_ = pty.Setsize(f, &pty.Winsize{
							Rows: msg.Rows,
							Cols: msg.Cols,
						})
					}
				}
			} else {
				// Plain text fallback (e.g. raw terminal input without JSON envelope)
				if _, err := f.Write(message); err != nil {
					break
				}
			}
		} else if mt == websocket.BinaryMessage {
			if _, err := f.Write(message); err != nil {
				break
			}
		}
	}

done:
	return nil
}
