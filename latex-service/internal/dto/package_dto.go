package dto

type TexPackage struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Category    string `json:"category"`
	Installed   bool   `json:"installed"`
}
