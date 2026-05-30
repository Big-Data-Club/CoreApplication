package dto

// SuccessResponse represents a successful API response.
type SuccessResponse struct {
	Success bool        `json:"success"`
	Message string      `json:"message,omitempty"`
	Data    interface{} `json:"data,omitempty"`
}

// ErrorResponse represents an error API response.
type ErrorResponse struct {
	Success bool   `json:"success"`
	Error   string `json:"error"`
	Message string `json:"message,omitempty"`
	Code    string `json:"code,omitempty"`
}

// PaginationRequest represents pagination parameters.
type PaginationRequest struct {
	Page     int `form:"page" binding:"omitempty,min=1"`
	PageSize int `form:"page_size" binding:"omitempty,min=1,max=100"`
}

// PaginationResponse represents pagination metadata.
type PaginationResponse struct {
	Page       int `json:"page"`
	PageSize   int `json:"page_size"`
	Total      int `json:"total"`
	TotalPages int `json:"total_pages"`
}

// ListResponse represents a paginated list response.
type ListResponse struct {
	Items      interface{}        `json:"items"`
	Pagination PaginationResponse `json:"pagination"`
}

func NewSuccessResponse(message string, data interface{}) *SuccessResponse {
	return &SuccessResponse{Success: true, Message: message, Data: data}
}

func NewDataResponse(data interface{}) *SuccessResponse {
	return &SuccessResponse{Success: true, Data: data}
}

func NewMessageResponse(message string) *SuccessResponse {
	return &SuccessResponse{Success: true, Message: message}
}

func NewErrorResponse(error string, message string) *ErrorResponse {
	return &ErrorResponse{Success: false, Error: error, Message: message}
}

func NewListResponse(items interface{}, page, pageSize, total int) *ListResponse {
	totalPages := (total + pageSize - 1) / pageSize
	return &ListResponse{
		Items: items,
		Pagination: PaginationResponse{
			Page: page, PageSize: pageSize,
			Total: total, TotalPages: totalPages,
		},
	}
}

// GetPagination calculates limit and offset from page params.
func (p *PaginationRequest) GetPagination() (limit, offset int) {
	page := p.Page
	if page < 1 {
		page = 1
	}
	pageSize := p.PageSize
	if pageSize < 1 {
		pageSize = 20
	}
	if pageSize > 100 {
		pageSize = 100
	}
	return pageSize, (page - 1) * pageSize
}
