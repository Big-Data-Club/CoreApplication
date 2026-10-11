package runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"lab-service/internal/config"
)

func TestValidPodName(t *testing.T) {
	valid := []string{"terminal-u2-l3-abc123", "a", "sandbox-42"}
	invalid := []string{"", "../secrets", "Terminal-1", "-terminal", "terminal-", "terminal/session"}
	for _, value := range valid {
		if !validPodName(value) {
			t.Fatalf("expected %q to be valid", value)
		}
	}
	for _, value := range invalid {
		if validPodName(value) {
			t.Fatalf("expected %q to be invalid", value)
		}
	}
}

func TestTerminalStartReusesWorkspaceAndReportsRealExpiry(t *testing.T) {
	created := time.Now().UTC().Truncate(time.Second)
	creates := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			creates++
			var pod map[string]interface{}
			_ = json.NewDecoder(r.Body).Decode(&pod)
			spec := pod["spec"].(map[string]interface{})
			if spec["securityContext"].(map[string]interface{})["fsGroup"] != float64(1000) {
				t.Error("workspace lacks fsGroup")
			}
			if spec["containers"].([]interface{})[0].(map[string]interface{})["workingDir"] != "/workspace" {
				t.Error("terminal starts outside workspace")
			}
			_, _ = w.Write([]byte(`{}`))
			return
		}
		if creates == 0 {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		_, _ = fmt.Fprintf(w, `{"metadata":{"name":"terminal-u2-l3","creationTimestamp":%q},"spec":{"activeDeadlineSeconds":3600},"status":{"phase":"Running"}}`, created.Format(time.RFC3339))
	}))
	defer server.Close()
	sandbox := &KubernetesTerminalSandbox{cfg: config.TerminalSandboxConfig{Namespace: "lab-sandbox", MaxSession: time.Hour, MaxMemoryMB: 512, MaxCPU: "500m", ProvisionTimeout: time.Second, PollInterval: time.Millisecond}, server: server.URL, client: server.Client()}
	for i := 0; i < 2; i++ {
		name, expires, err := sandbox.Start(context.Background(), 3, 2)
		if err != nil || name != "terminal-u2-l3" || !expires.Equal(created.Add(time.Hour)) {
			t.Fatalf("name=%s expires=%s err=%v", name, expires, err)
		}
	}
	if creates != 1 {
		t.Fatalf("reconnect created %d pods", creates)
	}
}

func TestTerminalRejectsOtherLearnerBeforeExec(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"metadata":{"labels":{"bdc.dev/user-id":"99","bdc.dev/lab-id":"3"}}}`))
	}))
	defer server.Close()
	sandbox := &KubernetesTerminalSandbox{cfg: config.TerminalSandboxConfig{Namespace: "lab-sandbox"}, server: server.URL, client: server.Client()}
	if _, _, err := sandbox.RunCommand(context.Background(), "terminal-u99-l3", 3, 2, "pwd"); err == nil {
		t.Fatal("other learner's terminal was accessible")
	}
}
