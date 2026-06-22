package handler

import (
	"bytes"
	"io"
	"net/http"
	"strconv"

	"latex-service/internal/dto"
	"latex-service/internal/service"

	"github.com/gin-gonic/gin"
)

type FileHandler struct {
	fileService *service.FileService
}

func NewFileHandler(fileService *service.FileService) *FileHandler {
	return &FileHandler{fileService: fileService}
}

// Upload handles uploading multiple files
func (h *FileHandler) Upload(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	form, err := c.MultipartForm()
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Failed to parse multipart form"))
		return
	}

	files := form.File["files"]
	if len(files) == 0 {
		// Fallback to singular "file" field
		file, header, err := c.Request.FormFile("file")
		if err == nil {
			defer file.Close()
			res, err := h.fileService.UploadFile(c.Request.Context(), userID, projectID, header.Filename, file, header.Size, header.Header.Get("Content-Type"))
			if err != nil {
				c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", err.Error()))
				return
			}
			c.JSON(http.StatusOK, dto.NewDataResponse([]*dto.FileResponse{res}))
			return
		}
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "No files uploaded"))
		return
	}

	var responses []*dto.FileResponse
	for _, fileHeader := range files {
		file, err := fileHeader.Open()
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to open uploaded file: "+fileHeader.Filename))
			return
		}

		res, err := h.fileService.UploadFile(c.Request.Context(), userID, projectID, fileHeader.Filename, file, fileHeader.Size, fileHeader.Header.Get("Content-Type"))
		file.Close()

		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to upload file "+fileHeader.Filename+": "+err.Error()))
			return
		}

		responses = append(responses, res)
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(responses))
}

// UploadZip handles uploading and extracting a ZIP archive
func (h *FileHandler) UploadZip(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	file, _, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "No zip file found in request"))
		return
	}
	defer file.Close()

	// Read ZIP to buffer to get io.ReaderAt and size
	zipBytes, err := io.ReadAll(file)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to read zip upload"))
		return
	}

	readerAt := bytes.NewReader(zipBytes)
	size := int64(len(zipBytes))

	res, err := h.fileService.ExtractAndUploadZip(c.Request.Context(), userID, projectID, readerAt, size)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("zip_extraction_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(res))
}

// List handles listing project files
func (h *FileHandler) List(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.fileService.ListFiles(c.Request.Context(), userID, projectID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(res))
}

// GetContent handles retrieving file content (usually text)
func (h *FileHandler) GetContent(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	fileIDStr := c.Param("fileId")
	fileID, err := strconv.ParseInt(fileIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid file ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	content, err := h.fileService.GetFileContent(c.Request.Context(), userID, projectID, fileID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(gin.H{"content": content}))
}

// UpdateContent handles updating file content
func (h *FileHandler) UpdateContent(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	fileIDStr := c.Param("fileId")
	fileID, err := strconv.ParseInt(fileIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid file ID"))
		return
	}

	var req dto.UpdateFileContentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	err = h.fileService.UpdateFileContent(c.Request.Context(), userID, projectID, fileID, req.Content)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("File content updated successfully"))
}

// Delete handles file deletion
func (h *FileHandler) Delete(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	fileIDStr := c.Param("fileId")
	fileID, err := strconv.ParseInt(fileIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid file ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	err = h.fileService.DeleteFile(c.Request.Context(), userID, projectID, fileID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("File deleted successfully"))
}

// Rename handles renaming a file in a project
func (h *FileHandler) Rename(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	fileIDStr := c.Param("fileId")
	fileID, err := strconv.ParseInt(fileIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid file ID"))
		return
	}

	var req dto.RenameFileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	err = h.fileService.RenameFile(c.Request.Context(), userID, projectID, fileID, req.Filename)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("File renamed successfully"))
}

// Create handles creating a new file with content
func (h *FileHandler) Create(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	var req dto.CreateFileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.fileService.CreateFile(c.Request.Context(), userID, projectID, req.Filename, req.Content)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(res))
}
