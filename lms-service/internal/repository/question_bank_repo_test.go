package repository

import "testing"

func TestJSONTextUsesValidTextAndDefaults(t *testing.T) {
	tests := []struct {
		name     string
		raw      []byte
		fallback string
		want     string
		wantErr  bool
	}{
		{name: "object", raw: []byte(`{"shuffle":true}`), fallback: "{}", want: `{"shuffle":true}`},
		{name: "empty array default", fallback: "[]", want: "[]"},
		{name: "empty object default", fallback: "{}", want: "{}"},
		{name: "invalid", raw: []byte(`{broken`), fallback: "{}", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := jsonText(tt.raw, tt.fallback, "field")
			if (err != nil) != tt.wantErr {
				t.Fatalf("jsonText() error = %v, wantErr %v", err, tt.wantErr)
			}
			if got != tt.want {
				t.Fatalf("jsonText() = %q, want %q", got, tt.want)
			}
		})
	}
}
