package dto

import "net/http"

// APIResponse is the standard JSON envelope for all HTTP responses.
type APIResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   *APIError   `json:"error,omitempty"`
}

type APIError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func OK(data interface{}) (int, APIResponse) {
	return http.StatusOK, APIResponse{Success: true, Data: data}
}

func Created(data interface{}) (int, APIResponse) {
	return http.StatusCreated, APIResponse{Success: true, Data: data}
}

func Err(code int, errCode, message string) (int, APIResponse) {
	return code, APIResponse{
		Success: false,
		Error:   &APIError{Code: errCode, Message: message},
	}
}

func ErrBadRequest(message string) (int, APIResponse) {
	return Err(http.StatusBadRequest, "bad_request", message)
}

func ErrUnauthorized(message string) (int, APIResponse) {
	return Err(http.StatusUnauthorized, "unauthorized", message)
}

func ErrForbidden(message string) (int, APIResponse) {
	return Err(http.StatusForbidden, "forbidden", message)
}

func ErrNotFound(message string) (int, APIResponse) {
	return Err(http.StatusNotFound, "not_found", message)
}

func ErrInternal(message string) (int, APIResponse) {
	return Err(http.StatusInternalServerError, "internal_error", message)
}
