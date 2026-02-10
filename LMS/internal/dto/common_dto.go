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
	Code    string `json:"code,omitempty"`
}

// PaginationRequest represents pagination parameters
type PaginationRequest struct {
	Page     int `form:"page" binding:"omitempty,min=1"`
	PageSize int `form:"page_size" binding:"omitempty,min=1,max=100"`
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

// IDResponse represents a response with just an ID
type IDResponse struct {
	ID int64 `json:"id"`
}

// MessageResponse represents a simple message response
type MessageResponse struct {
	Message string `json:"message"`
}

// BoolResponse represents a boolean response
type BoolResponse struct {
	Result bool `json:"result"`
}

// FilterRequest represents common filter parameters
type FilterRequest struct {
	Status   string `form:"status"`
	Category string `form:"category"`
	Level    string `form:"level"`
	Search   string `form:"search"`
	SortBy   string `form:"sort_by"`
	SortDir  string `form:"sort_dir" binding:"omitempty,oneof=asc desc"`
}

// Helper functions

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
func NewErrorResponse(error string, message string) *ErrorResponse {
	return &ErrorResponse{
		Success: false,
		Error:   error,
		Message: message,
	}
}

// NewListResponse creates a paginated list response
func NewListResponse(items interface{}, page, pageSize, total int) *ListResponse {
	totalPages := (total + pageSize - 1) / pageSize
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

// GetPagination calculates pagination values
func (p *PaginationRequest) GetPagination() (limit, offset int) {
	page := p.Page
	if page < 1 {
		page = 1
	}
	
	pageSize := p.PageSize
	if pageSize < 1 {
		pageSize = 20 // default page size
	}
	if pageSize > 100 {
		pageSize = 100 // max page size
	}
	
	limit = pageSize
	offset = (page - 1) * pageSize
	return
}