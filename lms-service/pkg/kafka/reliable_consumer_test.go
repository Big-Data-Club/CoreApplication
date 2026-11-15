package kafka

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	kafkago "github.com/segmentio/kafka-go"
)

type fakeReader struct {
	fetches, commits int
	cancel           context.CancelFunc
	message          kafkago.Message
}

func (r *fakeReader) FetchMessage(context.Context) (kafkago.Message, error) {
	r.fetches++
	return r.message, nil
}
func (r *fakeReader) CommitMessages(context.Context, ...kafkago.Message) error {
	r.commits++
	r.cancel()
	return nil
}
func TestConsumerCommitsOnlyAfterHandlerSuccess(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	r := &fakeReader{cancel: cancel}
	attempts := 0
	consume(ctx, r, func(context.Context, []byte) error {
		attempts++
		if r.commits != 0 {
			t.Error("commit preceded application")
		}
		if attempts == 1 {
			return errors.New("temporary database failure")
		}
		return nil
	}, func(context.Context, kafkago.Message, error) error {
		t.Fatal("transient error quarantined")
		return nil
	})
	if r.fetches != 1 || r.commits != 1 || attempts != 2 {
		t.Fatalf("fetch=%d commit=%d attempts=%d", r.fetches, r.commits, attempts)
	}
}
func TestConsumerQuarantinesInvalidJSONBeforeCommit(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	r := &fakeReader{cancel: cancel, message: kafkago.Message{Value: []byte("{")}}
	quarantined := false
	consume(ctx, r, func(_ context.Context, raw []byte) error {
		var value map[string]interface{}
		return json.Unmarshal(raw, &value)
	}, func(context.Context, kafkago.Message, error) error {
		if r.commits != 0 {
			t.Error("commit before quarantine")
		}
		quarantined = true
		return nil
	})
	if !quarantined || r.commits != 1 {
		t.Fatal("invalid event was lost")
	}
}

func TestDeadLetterPreservesNonUTF8Payload(t *testing.T) {
	original := []byte{0xff, 0x00, '{'}
	raw, err := json.Marshal(deadLetterEvent{Payload: original})
	if err != nil {
		t.Fatal(err)
	}
	var restored deadLetterEvent
	if err := json.Unmarshal(raw, &restored); err != nil {
		t.Fatal(err)
	}
	if string(restored.Payload) != string(original) {
		t.Fatal("malformed source bytes were not preserved")
	}
}
