package dto

// SuccessResponse represents a successful API response
type SuccessResponse struct {
	Success bool        `json:"success"`
	Message string      `json:"message,omitempty"`
	Data    interface{} `json:"data,omitempty"`
}

// ErrorResponse represents an error API response
type ErrorResponse struct {
	Success bool   `json:"success"`
	Error   string `json:"error"`
	Message string `json:"message,omitempty"`
}

// PaginationResponse represents pagination metadata
type PaginationResponse struct {
	Page       int `json:"page"`
	PageSize   int `json:"page_size"`
	Total      int `json:"total"`
	TotalPages int `json:"total_pages"`
}

// ListResponse represents a paginated list response
type ListResponse struct {
	Items      interface{}        `json:"items"`
	Pagination PaginationResponse `json:"pagination"`
}

// NewSuccessResponse creates a success response
func NewSuccessResponse(message string, data interface{}) *SuccessResponse {
	return &SuccessResponse{
		Success: true,
		Message: message,
		Data:    data,
	}
}

// NewDataResponse creates a success response with data only
func NewDataResponse(data interface{}) *SuccessResponse {
	return &SuccessResponse{
		Success: true,
		Data:    data,
	}
}

// NewMessageResponse creates a success response with message only
func NewMessageResponse(message string) *SuccessResponse {
	return &SuccessResponse{
		Success: true,
		Message: message,
	}
}

// NewErrorResponse creates an error response
func NewErrorResponse(err string, message string) *ErrorResponse {
	return &ErrorResponse{
		Success: false,
		Error:   err,
		Message: message,
	}
}

// NewListResponse creates a paginated list response
func NewListResponse(items interface{}, page, pageSize, total int) *ListResponse {
	totalPages := 0
	if pageSize > 0 {
		totalPages = (total + pageSize - 1) / pageSize
	}
	return &ListResponse{
		Items: items,
		Pagination: PaginationResponse{
			Page:       page,
			PageSize:   pageSize,
			Total:      total,
			TotalPages: totalPages,
		},
	}
}
