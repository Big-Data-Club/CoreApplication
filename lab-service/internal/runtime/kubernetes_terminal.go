package runtime

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
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
	name := fmt.Sprintf("terminal-u%d-l%d", userID, labID)
	if !validPodName(name) {
		return "", time.Time{}, fmt.Errorf("invalid session owner")
	}
	existing, err := s.sessionPod(ctx, name)
	if err == nil {
		expires := existing.Metadata.CreationTimestamp.Add(time.Duration(existing.Spec.ActiveDeadlineSeconds) * time.Second)
		if time.Now().Before(expires) && existing.Status.Phase != "Failed" && existing.Status.Phase != "Succeeded" {
			if err := s.waitRunning(ctx, name); err != nil {
				return "", time.Time{}, err
			}
			return name, expires, nil
		}
		s.Delete(ctx, name)
		deadline, cancel := context.WithTimeout(ctx, s.cfg.ProvisionTimeout)
		defer cancel()
		for {
			_, err = s.sessionPod(deadline, name)
			if isKubernetesStatus(err, http.StatusNotFound) {
				break
			}
			select {
			case <-deadline.Done():
				return "", time.Time{}, deadline.Err()
			case <-time.After(s.cfg.PollInterval):
			}
		}
	} else if !isKubernetesStatus(err, http.StatusNotFound) {
		return "", time.Time{}, err
	}

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
			"securityContext": map[string]interface{}{"runAsNonRoot": true, "runAsUser": 1000, "runAsGroup": 1000, "fsGroup": 1000, "seccompProfile": map[string]string{"type": "RuntimeDefault"}},
			"containers": []interface{}{map[string]interface{}{
				"name": "terminal", "image": s.cfg.Image, "imagePullPolicy": "IfNotPresent",
				"workingDir":      "/workspace",
				"command":         []string{"/bin/sh", "-c", "cd /workspace && exec sleep " + strconv.FormatInt(seconds, 10)},
				"env":             []interface{}{map[string]string{"name": "HOME", "value": "/workspace"}, map[string]string{"name": "TERM", "value": "xterm-256color"}},
				"resources":       map[string]interface{}{"requests": map[string]string{"cpu": "100m", "memory": "128Mi"}, "limits": map[string]string{"cpu": s.cfg.MaxCPU, "memory": strconv.Itoa(s.cfg.MaxMemoryMB) + "Mi"}},
				"securityContext": map[string]interface{}{"allowPrivilegeEscalation": false, "readOnlyRootFilesystem": true, "capabilities": map[string]interface{}{"drop": []string{"ALL"}}},
				"volumeMounts":    []interface{}{map[string]string{"name": "workspace", "mountPath": "/workspace"}, map[string]string{"name": "tmp", "mountPath": "/tmp"}},
			}},
			"volumes": []interface{}{map[string]interface{}{"name": "workspace", "emptyDir": map[string]string{"sizeLimit": "256Mi"}}, map[string]interface{}{"name": "tmp", "emptyDir": map[string]string{"sizeLimit": "64Mi"}}},
		},
	}
	if err := s.requestJSON(ctx, http.MethodPost, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods", pod, nil); err != nil && !isKubernetesStatus(err, http.StatusConflict) {
		return "", time.Time{}, err
	}
	if err := s.waitRunning(ctx, name); err != nil {
		s.Delete(context.Background(), name)
		return "", time.Time{}, err
	}
	created, err := s.sessionPod(ctx, name)
	if err != nil {
		return "", time.Time{}, err
	}
	return name, created.Metadata.CreationTimestamp.Add(time.Duration(created.Spec.ActiveDeadlineSeconds) * time.Second), nil
}

func (s *KubernetesTerminalSandbox) waitRunning(ctx context.Context, name string) error {
	ctx, cancel := context.WithTimeout(ctx, s.cfg.ProvisionTimeout)
	defer cancel()
	deadline := time.NewTimer(s.cfg.ProvisionTimeout)
	defer deadline.Stop()
	ticker := time.NewTicker(s.cfg.PollInterval)
	defer ticker.Stop()
	for {
		var pod struct {
			Status struct {
				Phase             string `json:"phase"`
				Message           string `json:"message"`
				ContainerStatuses []struct {
					State struct {
						Waiting *struct {
							Reason string `json:"reason"`
						} `json:"waiting"`
					} `json:"state"`
				} `json:"containerStatuses"`
			} `json:"status"`
		}
		if err := s.requestJSON(ctx, http.MethodGet, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods/"+name, nil, &pod); err != nil {
			return err
		}
		for _, container := range pod.Status.ContainerStatuses {
			if waiting := container.State.Waiting; waiting != nil {
				switch waiting.Reason {
				case "ErrImagePull", "ImagePullBackOff", "CreateContainerConfigError", "CreateContainerError":
					return fmt.Errorf("terminal image could not start: %s", waiting.Reason)
				}
			}
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
	query := url.Values{"container": {"terminal"}, "command": {"/bin/sh", "-c", "cd /workspace && exec /bin/sh -i"}, "stdin": {"true"}, "stdout": {"true"}, "stderr": {"true"}, "tty": {"true"}}
	endpoint := strings.Replace(s.server, "https://", "wss://", 1) + "/api/v1/namespaces/" + s.cfg.Namespace + "/pods/" + session + "/exec?" + query.Encode()
	header := http.Header{"Authorization": []string{"Bearer " + s.token}}
	upstream, resp, err := s.dialer.DialContext(ctx, endpoint, header)
	if err != nil {
		if resp != nil {
			resp.Body.Close()
		}
		return fmt.Errorf("open terminal exec stream: %w", err)
	}
	defer upstream.Close()
	browser.SetReadLimit(64 * 1024)
	upstream.SetReadLimit(128 * 1024)
	browser.SetReadDeadline(time.Now().Add(90 * time.Second))
	browser.SetPongHandler(func(string) error { return browser.SetReadDeadline(time.Now().Add(90 * time.Second)) })
	var workers sync.WaitGroup
	finished := make(chan struct{})
	defer func() { close(finished); browser.Close(); upstream.Close(); workers.Wait() }()
	workers.Add(1)
	go func() {
		defer workers.Done()
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-finished:
				return
			case <-ticker.C:
				_ = browser.WriteControl(websocket.PingMessage, nil, time.Now().Add(5*time.Second))
			}
		}
	}()
	errCh := make(chan error, 2)
	workers.Add(1)
	go func() {
		defer workers.Done()
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
	workers.Add(1)
	go func() {
		defer workers.Done()
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
	select {
	case err := <-errCh:
		return err
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (s *KubernetesTerminalSandbox) RunCommand(ctx context.Context, session string, labID, userID int64, command string) (string, bool, error) {
	if !validPodName(session) {
		return "", false, fmt.Errorf("invalid terminal session id")
	}
	var pod struct {
		Metadata struct {
			Labels map[string]string `json:"labels"`
		} `json:"metadata"`
	}
	if err := s.requestJSON(ctx, http.MethodGet, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods/"+session, nil, &pod); err != nil {
		return "", false, err
	}
	if pod.Metadata.Labels["bdc.dev/user-id"] != strconv.FormatInt(userID, 10) || pod.Metadata.Labels["bdc.dev/lab-id"] != strconv.FormatInt(labID, 10) {
		return "", false, fmt.Errorf("terminal session does not belong to this user or lab")
	}
	query := url.Values{"container": {"terminal"}, "command": {"/bin/sh", "-lc", command}, "stdin": {"false"}, "stdout": {"true"}, "stderr": {"true"}, "tty": {"false"}}
	endpoint := strings.Replace(s.server, "https://", "wss://", 1) + "/api/v1/namespaces/" + s.cfg.Namespace + "/pods/" + session + "/exec?" + query.Encode()
	upstream, resp, err := s.dialer.DialContext(ctx, endpoint, http.Header{"Authorization": []string{"Bearer " + s.token}})
	if err != nil {
		if resp != nil {
			resp.Body.Close()
		}
		return "", false, err
	}
	defer upstream.Close()
	upstream.SetReadLimit(128 * 1024)
	stop := make(chan struct{})
	defer close(stop)
	go func() {
		select {
		case <-ctx.Done():
			upstream.Close()
		case <-stop:
		}
	}()
	var output strings.Builder
	for {
		_, data, err := upstream.ReadMessage()
		if err != nil {
			return output.String(), false, err
		}
		if len(data) < 1 {
			continue
		}
		switch data[0] {
		case 1, 2:
			if output.Len() < 64*1024 {
				remaining := 64*1024 - output.Len()
				payload := data[1:]
				if len(payload) > remaining {
					payload = payload[:remaining]
				}
				output.Write(payload)
			}
		case 3:
			var status struct {
				Status string `json:"status"`
			}
			_ = json.Unmarshal(data[1:], &status)
			return strings.TrimSpace(output.String()), status.Status == "Success", nil
		}
	}
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
		return &kubernetesHTTPError{Code: resp.StatusCode, Message: fmt.Sprintf("Kubernetes API %s: %s", resp.Status, strings.TrimSpace(string(data)))}
	}
	if output != nil && len(data) > 0 {
		return json.Unmarshal(data, output)
	}
	return nil
}

type kubernetesHTTPError struct {
	Code    int
	Message string
}

func (e *kubernetesHTTPError) Error() string { return e.Message }
func isKubernetesStatus(err error, code int) bool {
	var apiErr *kubernetesHTTPError
	return errors.As(err, &apiErr) && apiErr.Code == code
}

type terminalPod struct {
	Metadata struct {
		Name              string    `json:"name"`
		CreationTimestamp time.Time `json:"creationTimestamp"`
	} `json:"metadata"`
	Spec struct {
		ActiveDeadlineSeconds int64 `json:"activeDeadlineSeconds"`
	} `json:"spec"`
	Status struct {
		Phase string `json:"phase"`
	} `json:"status"`
}

func (s *KubernetesTerminalSandbox) sessionPod(ctx context.Context, name string) (*terminalPod, error) {
	var pod terminalPod
	err := s.requestJSON(ctx, http.MethodGet, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods/"+name, nil, &pod)
	return &pod, err
}

// ActiveDeadlineSeconds stops processes, but bare Pods have no TTL controller.
// Sweep expired/terminated terminals, including leftovers after an API restart.
func (s *KubernetesTerminalSandbox) RunCleanup(ctx context.Context) {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		sweep, cancel := context.WithTimeout(ctx, 20*time.Second)
		var pods struct {
			Items []terminalPod `json:"items"`
		}
		if s.requestJSON(sweep, http.MethodGet, "/api/v1/namespaces/"+s.cfg.Namespace+"/pods?labelSelector="+url.QueryEscape("app.kubernetes.io/name=lab-terminal,app.kubernetes.io/managed-by=lab-service"), nil, &pods) == nil {
			for _, pod := range pods.Items {
				expires := pod.Metadata.CreationTimestamp.Add(time.Duration(pod.Spec.ActiveDeadlineSeconds) * time.Second)
				if pod.Status.Phase == "Succeeded" || pod.Status.Phase == "Failed" || time.Now().After(expires) {
					s.Delete(sweep, pod.Metadata.Name)
				}
			}
		}
		cancel()
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
