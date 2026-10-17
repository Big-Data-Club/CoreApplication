// Package dto contains the game HTTP contract. It has no database or gameplay
// dependencies, so request shapes can evolve without changing persistence.
package dto

type PlaceRequest struct {
	Kind string `json:"kind"`
	X    int    `json:"x"`
	Y    int    `json:"y"`
}

type EntityRequest struct {
	EntityID string `json:"entityId"`
}

type MoveRequest struct {
	EntityID string `json:"entityId"`
	X        int    `json:"x"`
	Y        int    `json:"y"`
}

type ItemQuantityRequest struct {
	Kind     string `json:"kind"`
	Quantity int    `json:"quantity"`
}

type CraftRequest struct {
	Recipe   string `json:"recipe"`
	Quantity int    `json:"quantity"`
}

type CatchRequest struct {
	InsectID string `json:"insectId"`
}

type ActionRequest struct {
	EntityID    string `json:"entityId"`
	Action      string `json:"action"`
	Item        string `json:"item"`
	ChallengeID string `json:"challenge_id"`
	Answer      string `json:"answer"`
}

type RenameRequest struct {
	Name string `json:"name"`
}

type ChallengeRequest struct {
	EntityID string `json:"entityId"`
	Action   string `json:"action"`
	Kind     string `json:"kind"`
}
