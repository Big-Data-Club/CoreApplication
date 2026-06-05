package handler

// wsMessage is the JSON protocol between the frontend xterm.js client and this backend.
// type = "input"  → data is raw terminal input bytes
// type = "resize" → cols/rows specify the new terminal dimensions
type wsMessage struct {
	Type string `json:"type"`
	Data string `json:"data,omitempty"`
	Cols uint16 `json:"cols,omitempty"`
	Rows uint16 `json:"rows,omitempty"`
}
