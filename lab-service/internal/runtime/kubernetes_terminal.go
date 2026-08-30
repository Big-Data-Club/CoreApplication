package runtime

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"lab-service/internal/config"

	"github.com/gorilla/websocket"
)

// KubernetesTerminalSandbox provisions one short-lived, network-isolated Pod
// per learner session and bridges xterm.js to the Kubernetes exec channel.
type KubernetesTerminalSandbox struct {
	cfg           config.TerminalSandboxConfig
	token, server string
	client        *http.Client
	dialer        *websocket.Dialer
}

func NewKubernetesTerminalSandbox(cfg config.TerminalSandboxConfig) (*KubernetesTerminalSandbox, error) {
	if !cfg.Enabled {
		return nil, nil
	}
	if cfg.ProvisionTimeout <= 0 {
		cfg.ProvisionTimeout = 90 * time.Second
	}
	if cfg.MaxSession <= 0 {
		cfg.MaxSession = time.Hour
	}
	if cfg.MaxMemoryMB <= 0 {
		cfg.MaxMemoryMB = 512
	}
	if cfg.MaxCPU == "" {
		cfg.MaxCPU = "500m"
	}
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 500 * time.Millisecond
	}
	token, err := os.ReadFile(serviceAccountTokenPath)
	if err != nil || strings.TrimSpace(string(token)) == "" {
		return nil, fmt.Errorf("terminal sandbox service-account token is unavailable")
	}
	ca, err := os.ReadFile(serviceAccountCAPath)
	if err != nil {
		return nil, fmt.Errorf("terminal sandbox cluster CA is unavailable: %w", err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(ca) {
		return nil, fmt.Errorf("terminal sandbox cluster CA is invalid")
	}
	tlsConfig := &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	return &KubernetesTerminalSandbox{
		cfg: cfg, token: strings.TrimSpace(string(token)), server: "https://kubernetes.default.svc",
		client: &http.Client{Timeout: cfg.ProvisionTimeout, Transport: &http.Transport{TLSClientConfig: tlsConfig}},
		dialer: &websocket.Dialer{TLSClientConfig: tlsConfig, HandshakeTimeout: 15 * time.Second, Subprotocols: []string{"v5.channel.k8s.io", "v4.channel.k8s.io"}},
	}, nil
}

func (s *KubernetesTerminalSandbox) Available() bool { return s != nil }

func (s *KubernetesTerminalSandbox) Start(ctx context.Context, labID, userID int64) (string, time.Time, error) {
	name := fmt.Sprintf("terminal-u%d-l%d-%x", userID, labID, time.Now().UnixNano()%0xfffffff)
	seconds := int64(s.cfg.MaxSession.Seconds())
	pod := map[string]interface{}{
		"apiVersion": "v1", "kind": "Pod",
		"metadata": map[string]interface{}{"name": name, "labels": map[string]string{
			"app.kubernetes.io/name": "lab-terminal", "app.kubernetes.io/managed-by": "lab-service",
			"bdc.dev/user-id": strconv.FormatInt(userID, 10), "bdc.dev/lab-id": strconv.FormatInt(labID, 10),
		}},
		"spec": map[string]interface{}{
			"serviceAccountName": "lab-sandbox-runner", "automountServiceAccountToken": false,
			"restartPolicy": "Never", "activeDeadlineSeconds": seconds, "terminationGracePeriodSeconds": 1,
			"securityContext": map[string]interface{}{"runAsNonRoot": true, "runAsUser": 1000, "runAsGroup": 1000, "seccompProfile": map[string]string{"type": "RuntimeDefault"}},
			"containers": []interface{}{map[string]interface{}{
				"name": "terminal", "image": s.cfg.Image, "imagePullPolicy": "IfNotPresent",
				"command":         []string{"/bin/sh", "-c", "cd /workspace && exec sleep " + strconv.FormatInt(seconds, 10)},
				"env":             []interface{}{map[string]string{"name": "HOME", "value": "/workspace"}, map[string]string{"name": "TERM", "value": "xterm-256color"}},
				"resources":       map[string]interface{}{"requests": map[string]string{"cpu": "100m", "memory": "128Mi"}, "limits": map[string]string{"cpu": s.cfg.MaxCPU, "memory": strconv.Itoa(s.cfg.MaxMemoryMB) + "Mi"}},
				"securityContext": map[string]interface{}{"allowPrivilegeEscalation": false, "readOnlyRootFilesystem": true, "capabilities": map[string]interface{}{"drop": []string{"ALL"}}},
				"volumeMounts":    []interface{}{map[string]string{"name": "workspace", "mountPath": "/workspace"}, map[string]string{"name": "tmp", "mountPath": "/tmp"}},
			}},
			"volumes": []interface{}{map[string]interface{}{"name": "workspace", "emptyDir": map[string]string{"sizeLimit": "256Mi"}}, map[string]interface{}{"name": "tmp", "emptyDir": map[string]string{"sizeLimit": "64Mi"}}},
		},
	}
	if err := s.requestJSON(ctx, http.MethodPost, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods", pod, nil); err != nil {
		return "", time.Time{}, err
	}
	if err := s.waitRunning(ctx, name); err != nil {
		s.Delete(context.Background(), name)
		return "", time.Time{}, err
	}
	return name, time.Now().Add(s.cfg.MaxSession), nil
}

func (s *KubernetesTerminalSandbox) waitRunning(ctx context.Context, name string) error {
	deadline := time.NewTimer(s.cfg.ProvisionTimeout)
	defer deadline.Stop()
	ticker := time.NewTicker(s.cfg.PollInterval)
	defer ticker.Stop()
	for {
		var pod struct {
			Status struct {
				Phase   string `json:"phase"`
				Message string `json:"message"`
			} `json:"status"`
		}
		if err := s.requestJSON(ctx, http.MethodGet, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods/"+name, nil, &pod); err != nil {
			return err
		}
		if pod.Status.Phase == "Running" {
			return nil
		}
		if pod.Status.Phase == "Failed" {
			return fmt.Errorf("terminal pod failed: %s", pod.Status.Message)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-deadline.C:
			return fmt.Errorf("terminal sandbox provisioning timed out")
		case <-ticker.C:
		}
	}
}

func (s *KubernetesTerminalSandbox) Bridge(ctx context.Context, browser *websocket.Conn, session string, labID, userID int64) error {
	if !validPodName(session) {
		return fmt.Errorf("invalid terminal session id")
	}
	var pod struct {
		Metadata struct {
			Labels map[string]string `json:"labels"`
		} `json:"metadata"`
	}
	if err := s.requestJSON(ctx, http.MethodGet, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods/"+session, nil, &pod); err != nil {
		return err
	}
	if pod.Metadata.Labels["bdc.dev/user-id"] != strconv.FormatInt(userID, 10) || pod.Metadata.Labels["bdc.dev/lab-id"] != strconv.FormatInt(labID, 10) {
		return fmt.Errorf("terminal session does not belong to this user or lab")
	}
	defer s.Delete(context.Background(), session)
	query := url.Values{"container": {"terminal"}, "command": {"/bin/sh"}, "stdin": {"true"}, "stdout": {"true"}, "stderr": {"true"}, "tty": {"true"}}
	endpoint := "wss://kubernetes.default.svc/api/v1/namespaces/" + s.cfg.Namespace + "/pods/" + session + "/exec?" + query.Encode()
	header := http.Header{"Authorization": []string{"Bearer " + s.token}}
	upstream, resp, err := s.dialer.DialContext(ctx, endpoint, header)
	if err != nil {
		if resp != nil {
			resp.Body.Close()
		}
		return fmt.Errorf("open terminal exec stream: %w", err)
	}
	defer upstream.Close()
	errCh := make(chan error, 2)
	go func() {
		for {
			_, data, err := upstream.ReadMessage()
			if err != nil {
				errCh <- err
				return
			}
			if len(data) > 1 && (data[0] == 1 || data[0] == 2) {
				if err := browser.WriteMessage(websocket.BinaryMessage, data[1:]); err != nil {
					errCh <- err
					return
				}
			}
		}
	}()
	go func() {
		for {
			mt, data, err := browser.ReadMessage()
			if err != nil {
				errCh <- err
				return
			}
			if mt == websocket.TextMessage {
				var msg struct {
					Type, Data string
					Cols, Rows uint16
				}
				if json.Unmarshal(data, &msg) == nil {
					if msg.Type == "resize" {
						payload, _ := json.Marshal(map[string]uint16{"Width": msg.Cols, "Height": msg.Rows})
						data = append([]byte{4}, payload...)
					} else {
						data = append([]byte{0}, []byte(msg.Data)...)
					}
				} else {
					data = append([]byte{0}, data...)
				}
			} else {
				data = append([]byte{0}, data...)
			}
			if err := upstream.WriteMessage(websocket.BinaryMessage, data); err != nil {
				errCh <- err
				return
			}
		}
	}()
	return <-errCh
}

func validPodName(value string) bool {
	if len(value) < 1 || len(value) > 63 || value[0] < 'a' || value[0] > 'z' {
		return false
	}
	for _, char := range value {
		if (char < 'a' || char > 'z') && (char < '0' || char > '9') && char != '-' {
			return false
		}
	}
	return value[len(value)-1] != '-'
}

func (s *KubernetesTerminalSandbox) Delete(ctx context.Context, name string) {
	_ = s.requestJSON(ctx, http.MethodDelete, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods/"+name, nil, nil)
}

func (s *KubernetesTerminalSandbox) requestJSON(ctx context.Context, method, path string, body, output interface{}) error {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(encoded)
	}
	req, err := http.NewRequestWithContext(ctx, method, s.server+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+s.token)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 128*1024))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("Kubernetes API %s: %s", resp.Status, strings.TrimSpace(string(data)))
	}
	if output != nil && len(data) > 0 {
		return json.Unmarshal(data, output)
	}
	return nil
}
