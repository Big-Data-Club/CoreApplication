//go:build !windows

package handler

import (
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

	// Configure process group so we can kill child processes together
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Setpgid: true,
	}

	// Try standard pty.Start (sets Setctty = true under the hood)
	f, err := pty.Start(cmd)
	if err != nil {
		log.Printf("[TerminalWS] pty.Start failed: %v, attempting fallback without controlling TTY (Setctty=false)", err)
		
		// Fallback: Open PTY pair manually and start process without Setctty=true
		var tty *os.File
		f, tty, err = pty.Open()
		if err != nil {
			log.Printf("[TerminalWS] pty.Open failed in fallback: %v", err)
			return err
		}
		defer tty.Close()

		cmd.Stdin = tty
		cmd.Stdout = tty
		cmd.Stderr = tty

		// Ensure SysProcAttr is set correctly but with Setctty disabled
		cmd.SysProcAttr = &syscall.SysProcAttr{
			Setpgid: true,
			Setsid:  true,
		}

		if err = cmd.Start(); err != nil {
			f.Close()
			log.Printf("[TerminalWS] cmd.Start failed in fallback: %v", err)
			return err
		}
	}
	defer f.Close()

	var once sync.Once
	killProcess := func() {
		once.Do(func() {
			if cmd.Process != nil {
				// Kill the entire process group to prevent orphan processes
				_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
			}
		})
	}
	defer killProcess()

	// Read output from PTY and write to WebSocket
	go func() {
		buf := make([]byte, 1024)
		for {
			n, err := f.Read(buf)
			if n > 0 {
				_ = ws.WriteMessage(websocket.BinaryMessage, buf[:n])
			}
			if err != nil {
				break
			}
		}
		_ = ws.Close()
	}()

	// Read input from WebSocket and write to PTY
	for {
		mt, message, err := ws.ReadMessage()
		if err != nil {
			break
		}
		if mt == websocket.TextMessage || mt == websocket.BinaryMessage {
			_, err = f.Write(message)
			if err != nil {
				break
			}
		}
	}
	return nil
}
