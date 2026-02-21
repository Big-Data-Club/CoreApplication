package handler

import (
	"fmt"
	"net/http"
	"path/filepath"
	"strings"
	"time"
	"unicode"

	"example/hello/internal/dto"
	"example/hello/pkg/logger"
	"example/hello/pkg/storage"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type FileHandler struct {
	storage storage.Storage
}

func NewFileHandler(storage storage.Storage) *FileHandler {
	return &FileHandler{
		storage: storage,
	}
}

// FileUploadResponse represents the response after file upload
type FileUploadResponse struct {
	FileID   string `json:"file_id" example:"550e8400-e29b-41d4-a716-446655440000"`
	FileName string `json:"file_name" example:"document.pdf"`
	FileURL  string `json:"file_url" example:"/api/v1/files/serve/document/20240101120000_550e8400_document.pdf"`
	FilePath string `json:"file_path" example:"document/20240101120000_550e8400_document.pdf"`
	FileSize int64  `json:"file_size" example:"1024000"`
	FileType string `json:"file_type" example:"document"`
}

// UploadFile godoc
// @Summary Upload a file
// @Description Upload a file to storage (video, document, or image)
// @Tags Files
// @Accept multipart/form-data
// @Produce json
// @Param file formData file true "File to upload"
// @Param type formData string false "File type (video, document, image)" default(document)
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=FileUploadResponse} "File uploaded successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid file or file type not allowed"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /files/upload [post]
func (h *FileHandler) UploadFile(c *gin.Context) {
	// Get file from request
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_file", "No file uploaded"))
		return
	}

	// Get file type
	fileType := c.PostForm("type")
	if fileType == "" {
		fileType = "document"
	}

	// Validate file extension
	ext := strings.ToLower(filepath.Ext(file.Filename))
	if !isValidFileType(fileType, file.Filename) {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse(
			"invalid_file_type", 
			fmt.Sprintf("File type %s is not allowed for %s uploads. Got: %s", ext, fileType, file.Filename),
		))
		return
	}

	// Check file size (max 100MB)
	const maxFileSize = 100 * 1024 * 1024
	if file.Size > maxFileSize {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse(
			"file_too_large", 
			fmt.Sprintf("File size %.2f MB exceeds maximum of 100MB", float64(file.Size)/(1024*1024)),
		))
		return
	}

	// Log upload attempt
	logger.Info(fmt.Sprintf("Processing file upload: %s (%.2f MB, type: %s)", 
		file.Filename, float64(file.Size)/(1024*1024), fileType))

	// Open file
	src, err := file.Open()
	if err != nil {
		logger.Error("Failed to open uploaded file", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to process file"))
		return
	}
	defer src.Close()

	// Generate unique filename
	fileID := uuid.New().String()
	timestamp := time.Now().Format("20060102150405")
	
	// Clean original filename (remove special characters)
	cleanName := cleanFilename(file.Filename)
	nameWithoutExt := strings.TrimSuffix(cleanName, ext)
	
	// Create stored filename: type/YYYYMMDDHHMMSS_uuid_originalname.ext
	storedFilename := fmt.Sprintf("%s/%s_%s_%s%s", fileType, timestamp, fileID[:8], nameWithoutExt, ext)

	// Detect content type từ extension để lưu đúng metadata (quan trọng với MinIO)
	contentType := getContentType(file.Filename)

	// Stream trực tiếp từ multipart reader vào storage — không buffer vào RAM
	_, err = h.storage.Upload(c.Request.Context(), storedFilename, src, file.Size, contentType)
	if err != nil {
		logger.Error("Failed to upload file to storage", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to upload file"))
		return
	}

	// Generate public URL (full URL)
	publicURL := fmt.Sprintf("/files/%s", storedFilename)
	
	logger.Info(fmt.Sprintf("File uploaded successfully: %s -> %s", file.Filename, storedFilename))

	// Return response
	response := FileUploadResponse{
		FileID:   fileID,
		FileName: file.Filename,
		FileURL:  publicURL,
		FilePath: storedFilename,
		FileSize: file.Size,
		FileType: fileType,
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(response))
}

// ServeFile godoc
// @Summary Serve a file
// @Description Serve a file directly for viewing in browser (public access)
// @Tags Files
// @Produce application/octet-stream
// @Param filepath path string true "File path"
// @Success 200 {file} binary "File content"
// @Success 206 {file} binary "Partial file content (Range request)"
// @Failure 400 {object} dto.ErrorResponse "Invalid filename"
// @Failure 404 {object} dto.ErrorResponse "File not found"
// @Router /files/serve/{filepath} [get]
func (h *FileHandler) ServeFile(c *gin.Context) {
	filename, ok := sanitizeFilePath(c.Param("filepath"))
	if !ok {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_filename", "Invalid file path"))
		return
	}

	logger.Info(fmt.Sprintf("Serving file: %s", filename))

	result, err := h.storage.GetObject(c.Request.Context(), filename)
	if err != nil {
		logger.Error(fmt.Sprintf("Failed to serve file %s", filename), err)
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
		return
	}
	defer result.Body.Close()

	// CORS cho file serving (cho phép embed từ bất kỳ website nào)
	c.Header("Access-Control-Allow-Origin", "*")
	c.Header("Access-Control-Allow-Methods", "GET, OPTIONS")

	// Inline cho image/video/PDF, attachment cho loại khác
	ext := strings.ToLower(filepath.Ext(filename))
	if isImage(ext) || isVideo(ext) || ext == ".pdf" {
		c.Header("Content-Disposition", "inline")
	} else {
		c.Header("Content-Disposition", fmt.Sprintf(`inline; filename="%s"`, filepath.Base(filename)))
	}

	// Filename trong MinIO có timestamp nên content không đổi → immutable cache
	c.Header("Cache-Control", "public, max-age=31536000, immutable")

	if result.ETag != "" {
		c.Header("ETag", result.ETag)
	}

	// Detect content type từ extension (ưu tiên hơn metadata MinIO nếu rỗng)
	contentType := result.ContentType
	if contentType == "" || contentType == "application/octet-stream" {
		contentType = getContentType(filename)
	}

	// http.ServeContent tự động:
	//   ✓ Handle Range/Partial Content → video player seek được
	//   ✓ Set Content-Length và Content-Type
	//   ✓ Handle If-Modified-Since, ETag (304 Not Modified)
	//   ✓ Stream từ storage đến client, không buffer vào RAM
	c.Writer.Header().Set("Content-Type", contentType)
	http.ServeContent(c.Writer, c.Request, filepath.Base(filename), result.LastModified, result.Body)
}

// DownloadFile godoc
// @Summary Download a file
// @Description Download a file with attachment disposition (requires authentication)
// @Tags Files
// @Produce application/octet-stream
// @Param filepath path string true "File path"
// @Security BearerAuth
// @Success 200 {file} binary "File content"
// @Success 206 {file} binary "Partial file content"
// @Failure 400 {object} dto.ErrorResponse "Invalid filename"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 404 {object} dto.ErrorResponse "File not found"
// @Router /files/download/{filepath} [get]
func (h *FileHandler) DownloadFile(c *gin.Context) {
	filename, ok := sanitizeFilePath(c.Param("filepath"))
	if !ok {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_filename", "Invalid file path"))
		return
	}

	logger.Info(fmt.Sprintf("Downloading file: %s", filename))

	result, err := h.storage.GetObject(c.Request.Context(), filename)
	if err != nil {
		logger.Error(fmt.Sprintf("Failed to download file %s", filename), err)
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
		return
	}
	defer result.Body.Close()

	baseName := filepath.Base(filename)
	// attachment: buộc browser download thay vì mở inline
	c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, baseName))

	http.ServeContent(c.Writer, c.Request, baseName, result.LastModified, result.Body)
}

// DeleteFile godoc
// @Summary Delete a file
// @Description Delete a file from storage (admin/teacher only)
// @Tags Files
// @Produce json
// @Param filepath path string true "File path"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "File deleted successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid filename"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - admin/teacher only"
// @Failure 404 {object} dto.ErrorResponse "File not found"
// @Failure 500 {object} dto.ErrorResponse "Failed to delete file"
// @Router /files/delete/{filepath} [delete]
func (h *FileHandler) DeleteFile(c *gin.Context) {
	filename, ok := sanitizeFilePath(c.Param("filepath"))
	if !ok {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_filename", "Invalid file path"))
		return
	}

	logger.Info(fmt.Sprintf("Deleting file: %s", filename))

	// Delete from storage
	if err := h.storage.Delete(c.Request.Context(), filename); err != nil {
		logger.Error(fmt.Sprintf("Failed to delete file %s", filename), err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("delete_failed", "Failed to delete file"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("File deleted successfully"))
}

// ============================================
// HELPER FUNCTIONS
// ============================================

// sanitizeFilePath làm sạch và validate đường dẫn để chống path traversal.
// Input "/document/20240101_abc.pdf" → "document/20240101_abc.pdf", true
// Input "../../etc/passwd"           → "", false
func sanitizeFilePath(rawPath string) (string, bool) {
	cleaned := strings.TrimPrefix(rawPath, "/")
	if cleaned == "" {
		return "", false
	}

	// filepath.Clean resolve .., ., double slashes
	cleaned = filepath.Clean(cleaned)

	// Chặn path traversal và absolute path
	if strings.HasPrefix(cleaned, "..") || filepath.IsAbs(cleaned) {
		return "", false
	}

	// Chỉ cho phép ký tự an toàn
	for _, r := range cleaned {
		if !isAllowedPathChar(r) {
			return "", false
		}
	}

	return cleaned, true
}

func isAllowedPathChar(r rune) bool {
	return unicode.IsLetter(r) || unicode.IsDigit(r) ||
		r == '/' || r == '-' || r == '_' || r == '.' || r == ' '
}

// cleanFilename sanitizes a filename để lưu an toàn.
func cleanFilename(filename string) string {
	clean := filepath.Base(filename)
	ext := filepath.Ext(clean)
	nameWithoutExt := strings.TrimSuffix(clean, ext)

	var builder strings.Builder
	for _, r := range nameWithoutExt {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '-' || r == '_' || r == '.' {
			builder.WriteRune(r)
		} else {
			builder.WriteRune('_')
		}
	}

	clean = strings.Trim(builder.String(), "_")
	if clean == "" {
		clean = "file"
	}
	if len(clean) > 50 {
		clean = clean[:50]
	}

	return clean + ext
}

func isValidFileType(fileType, filename string) bool {
	ext := strings.ToLower(filepath.Ext(filename))
	
	allowedTypes := map[string][]string{
		"video":    {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"},
		"document": {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".csv"},
		"image":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"},
	}

	if allowed, ok := allowedTypes[fileType]; ok {
		for _, allowedExt := range allowed {
			if ext == allowedExt {
				return true
			}
		}
		return false
	}

	// If fileType not specified or unknown, allow all common types
	allAllowed := []string{
		".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v",
		".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".csv",
		".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
	}
	
	for _, allowedExt := range allAllowed {
		if ext == allowedExt {
			return true
		}
	}
	
	return false
}

func getContentType(filename string) string {
	ext := strings.ToLower(filepath.Ext(filename))
	
	contentTypes := map[string]string{
		// Images
		".jpg":  "image/jpeg",
		".jpeg": "image/jpeg",
		".png":  "image/png",
		".gif":  "image/gif",
		".webp": "image/webp",
		".svg":  "image/svg+xml",
		".bmp":  "image/bmp",
		
		// Videos
		".mp4":  "video/mp4",
		".webm": "video/webm",
		".avi":  "video/x-msvideo",
		".mov":  "video/quicktime",
		".mkv":  "video/x-matroska",
		".m4v":  "video/x-m4v",
		".flv":  "video/x-flv",
		".wmv":  "video/x-ms-wmv",
		
		// Documents
		".pdf":  "application/pdf",
		".doc":  "application/msword",
		".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		".xls":  "application/vnd.ms-excel",
		".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		".ppt":  "application/vnd.ms-powerpoint",
		".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
		".txt":  "text/plain",
		".csv":  "text/csv",
	}
	
	if contentType, ok := contentTypes[ext]; ok {
		return contentType
	}
	
	return "application/octet-stream"
}

func isImage(ext string) bool {
	imageExts := []string{".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}
	for _, imgExt := range imageExts {
		if ext == imgExt {
			return true
		}
	}
	return false
}

func isVideo(ext string) bool {
	videoExts := []string{".mp4", ".webm", ".avi", ".mov", ".mkv", ".m4v", ".flv", ".wmv"}
	for _, vidExt := range videoExts {
		if ext == vidExt {
			return true
		}
	}
	return false
}