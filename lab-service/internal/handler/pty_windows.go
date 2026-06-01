//go:build windows

package handler

import (
	"os/exec"
	"sync"

	"github.com/gorilla/websocket"
)

func startShellPTY(cmd *exec.Cmd, ws *websocket.Conn) error {
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	defer stdin.Close()

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}

	if err := cmd.Start(); err != nil {
		return err
	}

	var once sync.Once
	killProcess := func() {
		once.Do(func() {
			if cmd.Process != nil {
				_ = cmd.Process.Kill()
			}
		})
	}
	defer killProcess()

	// Read from stdout and write to WS
	go func() {
		buf := make([]byte, 1024)
		for {
			n, err := stdout.Read(buf)
			if n > 0 {
				_ = ws.WriteMessage(websocket.BinaryMessage, buf[:n])
			}
			if err != nil {
				break
			}
		}
		_ = ws.Close()
	}()

	// Read from stderr and write to WS
	go func() {
		buf := make([]byte, 1024)
		for {
			n, err := stderr.Read(buf)
			if n > 0 {
				_ = ws.WriteMessage(websocket.BinaryMessage, buf[:n])
			}
			if err != nil {
				break
			}
		}
		_ = ws.Close()
	}()

	// Read from WS and write to stdin
	for {
		mt, message, err := ws.ReadMessage()
		if err != nil {
			break
		}
		if mt == websocket.TextMessage || mt == websocket.BinaryMessage {
			_, err = stdin.Write(message)
			if err != nil {
				break
			}
		}
	}
	return nil
}
