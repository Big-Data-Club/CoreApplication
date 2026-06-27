package handler

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"example/hello/internal/config"
	"example/hello/internal/dto"
	"example/hello/pkg/logger"
	"example/hello/pkg/storage"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type FileHandler struct {
	storage storage.Storage
	config  config.UploadConfig
}

func NewFileHandler(storage storage.Storage, cfg config.UploadConfig) *FileHandler {
	return &FileHandler{
		storage: storage,
		config:  cfg,
	}
}

type FileUploadResponse struct {
	FileID   string `json:"file_id"`
	FileName string `json:"file_name"`
	FileURL  string `json:"file_url"`
	FilePath string `json:"file_path"`
	FileSize int64  `json:"file_size"`
	FileType string `json:"file_type"`
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
// @Success 200 {object} dto.SuccessResponse{data=FileUploadResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /files/upload [post]
func (h *FileHandler) UploadFile(c *gin.Context) {
	reader, err := c.Request.MultipartReader()
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Failed to process multipart form"))
		return
	}

	var fileType string = "document"
	var uploadedResponse *FileUploadResponse

	for {
		part, err := reader.NextPart()
		if err != nil {
			if err == io.EOF {
				break
			}
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("upload_error", "Error reading file stream"))
			return
		}

		formName := part.FormName()

		if formName == "type" {
			buf := make([]byte, 100)
			n, _ := part.Read(buf)
			fileType = strings.TrimSpace(string(buf[:n]))
			part.Close()
			continue
		}

		if formName != "file" {
			part.Close()
			continue
		}

		filename := part.FileName()
		if filename == "" {
			part.Close()
			continue
		}

		// Auto-detect file type from extension if not explicitly provided or mismatched
		ext := strings.ToLower(filepath.Ext(filename))
		if fileType == "document" {
			// Try to auto-detect from extension
			detectedType := detectFileTypeFromExt(ext)
			if detectedType != "document" {
				fileType = detectedType
			}
		}

		// Validate extension
		if !isValidFileType(fileType, filename) {
			part.Close()
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse(
				"invalid_file_type",
				fmt.Sprintf("File type %s is not allowed for %s uploads.", ext, fileType),
			))
			return
		}

		tmpFile, err := os.CreateTemp("", "upload-*"+filepath.Ext(filename))
		if err != nil {
			part.Close()
			logger.Error("Failed to create temp file", err)
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to process file"))
			return
		}
		tmpPath := tmpFile.Name()

		fileSize, err := io.Copy(tmpFile, part)
		tmpFile.Close()
		part.Close()

		if err != nil {
			os.Remove(tmpPath)
			logger.Error("Failed to buffer upload to temp file", err)
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to read uploaded file"))
			return
		}

		if h.config.MaxSize > 0 && fileSize > h.config.MaxSize {
			os.Remove(tmpPath)
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse(
				"file_too_large",
				fmt.Sprintf("File exceeds maximum size of %d MB", h.config.MaxSize/1024/1024),
			))
			return
		}

		fileID := uuid.New().String()
		timestamp := time.Now().Format("20060102150405")
		ext = strings.ToLower(filepath.Ext(filename))
		cleanName := cleanFilename(filename)
		nameWithoutExt := strings.TrimSuffix(cleanName, ext)
		storedFilename := fmt.Sprintf("%s/%s_%s_%s%s", fileType, timestamp, fileID[:8], nameWithoutExt, ext)
		contentType := getContentType(filename)

		tmpReader, err := os.Open(tmpPath)
		if err != nil {
			os.Remove(tmpPath)
			logger.Error("Failed to re-open temp file for upload", err)
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to process file"))
			return
		}

		logger.Info(fmt.Sprintf("Uploading %s (%.1f MB) to MinIO as %s", filename, float64(fileSize)/1024/1024, storedFilename))

		_, err = h.storage.Upload(c.Request.Context(), storedFilename, tmpReader, fileSize, contentType)
		tmpReader.Close()
		os.Remove(tmpPath)

		if err != nil {
			logger.Error(fmt.Sprintf("MinIO upload failed for %s", filename), err)
			errMsg := "Failed to upload file"
			if strings.Contains(err.Error(), "context canceled") || strings.Contains(err.Error(), "context deadline exceeded") {
				errMsg = "Upload timed out - the file may be too large or the connection was lost"
			}
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", errMsg))
			return
		}

		uploadedResponse = &FileUploadResponse{
			FileID:   fileID,
			FileName: filename,
			FileURL:  fmt.Sprintf("/files/%s", storedFilename),
			FilePath: storedFilename,
			FileSize: fileSize,
			FileType: fileType,
		}
	}

	if uploadedResponse == nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_file", "No file found in request"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(uploadedResponse))
}

// ServeFile godoc
// @Summary Serve a file for inline viewing
// @Tags Files
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

	result, err := h.storage.GetObject(c.Request.Context(), filename)
	if err != nil {
		if strings.Contains(err.Error(), "file not found") {
			logger.Warn(fmt.Sprintf("File not found when serving %s: %v", filename, err))
			ext := strings.ToLower(filepath.Ext(filename))
			if isImage(ext) {
				c.Header("Content-Type", "image/svg+xml")
				c.Header("Cache-Control", "public, max-age=3600")
				svg := `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
					<rect width="100%" height="100%" fill="#eee"/>
					<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#aaa">Image Not Found</text>
				</svg>`
				c.String(http.StatusNotFound, svg)
				return
			}
		} else {
			logger.Error(fmt.Sprintf("Failed to serve file %s", filename), err)
		}
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
		return
	}
	defer result.Body.Close()

	c.Header("Access-Control-Allow-Origin", "*")
	c.Header("Access-Control-Allow-Methods", "GET, OPTIONS")

	ext := strings.ToLower(filepath.Ext(filename))
	if isImage(ext) || isVideo(ext) || ext == ".pdf" {
		c.Header("Content-Disposition", "inline")
	} else {
		c.Header("Content-Disposition", fmt.Sprintf(`inline; filename="%s"`, filepath.Base(filename)))
	}

	c.Header("Cache-Control", "public, max-age=31536000, immutable")
	if result.ETag != "" {
		c.Header("ETag", result.ETag)
	}

	contentType := result.ContentType
	if contentType == "" || contentType == "application/octet-stream" {
		contentType = getContentType(filename)
	}

	c.Writer.Header().Set("Content-Type", contentType)
	http.ServeContent(c.Writer, c.Request, filepath.Base(filename), result.LastModified, result.Body)
}

// DownloadFile godoc
// @Summary Download a file as attachment
// @Tags Files
// @Produce application/octet-stream
// @Param filepath path string true "File path"
// @Success 200 {file} binary "File content"
// @Success 206 {file} binary "Partial file content"
// @Failure 400 {object} dto.ErrorResponse "Invalid filename"
// @Failure 404 {object} dto.ErrorResponse "File not found"
// @Router /files/download/{filepath} [get]
func (h *FileHandler) DownloadFile(c *gin.Context) {
	filename, ok := sanitizeFilePath(c.Param("filepath"))
	if !ok {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_filename", "Invalid file path"))
		return
	}

	result, err := h.storage.GetObject(c.Request.Context(), filename)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
		return
	}
	defer result.Body.Close()

	baseName := filepath.Base(filename)
	c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, baseName))
	http.ServeContent(c.Writer, c.Request, baseName, result.LastModified, result.Body)
}

// DeleteFile godoc
// @Summary Delete a file
// @Tags Files
// @Produce json
// @Param filepath path string true "File path"
// @Success 200 {object} dto.SuccessResponse{message=string} "File deleted successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid filename"
// @Failure 404 {object} dto.ErrorResponse "File not found"
// @Failure 500 {object} dto.ErrorResponse "Failed to delete file"
// @Router /files/delete/{filepath} [delete]
func (h *FileHandler) DeleteFile(c *gin.Context) {
	filename, ok := sanitizeFilePath(c.Param("filepath"))
	if !ok {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_filename", "Invalid file path"))
		return
	}

	if err := h.storage.Delete(c.Request.Context(), filename); err != nil {
		logger.Error(fmt.Sprintf("Failed to delete file %s", filename), err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("delete_failed", "Failed to delete file"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("File deleted successfully"))
}

// GetPresignedURL godoc
// @Summary Get presigned URL for a file (for remote access)
// @Description Generate a temporary presigned URL for accessing a file directly from MinIO.
// @Description Useful for VLM image descriptions and external integrations.
// @Tags Files
// @Produce json
// @Param filepath path string true "File path"
// @Param expires query int false "Expiration in seconds" default(3600)
// @Success 200 {object} dto.SuccessResponse{data=map[string]interface{}} "Presigned URL"
// @Failure 400 {object} dto.ErrorResponse "Invalid filename"
// @Failure 404 {object} dto.ErrorResponse "File not found"
// @Failure 500 {object} dto.ErrorResponse "Failed to generate presigned URL"
// @Router /files/presigned/{filepath} [get]
func (h *FileHandler) GetPresignedURL(c *gin.Context) {
	filename, ok := sanitizeFilePath(c.Param("filepath"))
	if !ok {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_filename", "Invalid file path"))
		return
	}

	expiresStr := c.DefaultQuery("expires", "3600")
	expires, err := strconv.Atoi(expiresStr)
	if err != nil || expires <= 0 || expires > 24*3600 {
		expires = 3600 // default 1 hour
	}

	// Check file exists first
	result, err := h.storage.GetObject(c.Request.Context(), filename)
	if err != nil {
		if strings.Contains(err.Error(), "file not found") {
			logger.Warn(fmt.Sprintf("File not found when generating presigned URL for %s: %v", filename, err))
		} else {
			logger.Error(fmt.Sprintf("Failed to check file %s", filename), err)
		}
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
		return
	}
	result.Body.Close()

	// Cast to MinIO storage and generate presigned URL
	minioStorage, ok := h.storage.(*storage.MinIOStorage)
	if !ok {
		logger.Error("Storage is not MinIO, cannot generate presigned URL", nil)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("unsupported", "Presigned URLs not supported for this storage backend"))
		return
	}

	presignedURL, err := minioStorage.GetPresignedURL(c.Request.Context(), filename, time.Duration(expires)*time.Second)
	if err != nil {
		logger.Error(fmt.Sprintf("Failed to generate presigned URL for %s", filename), err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("presign_failed", "Failed to generate presigned URL"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"file_path":      filename,
		"presigned_url":  presignedURL,
		"expires_in_sec": expires,
	}))
}

func sanitizeFilePath(rawPath string) (string, bool) {
	// Gin's wildcard parameter (*filepath) always retains the leading slash (e.g., "/document/file.pdf").
	// We check and trim a single leading slash so we can validate and use it as a relative object key.
	cleanedRaw := rawPath
	if strings.HasPrefix(cleanedRaw, "/") {
		cleanedRaw = cleanedRaw[1:]
	}

	if strings.HasPrefix(cleanedRaw, "/") || path.IsAbs(cleanedRaw) {
		return "", false
	}

	decoded, err := url.PathUnescape(rawPath)
	if err != nil {
		decoded = rawPath
	}

	decoded = toUTF8(decoded)

	cleaned := strings.TrimPrefix(decoded, "/")
	if cleaned == "" {
		return "", false
	}
	cleaned = path.Clean(cleaned)
	if strings.HasPrefix(cleaned, "..") || path.IsAbs(cleaned) {
		return "", false
	}
	for _, r := range cleaned {
		if !isAllowedPathChar(r) {
			return "", false
		}
	}
	return cleaned, true
}

func toUTF8(s string) string {
	if utf8.ValidString(s) {
		return s
	}
	runes := make([]rune, 0, len(s))
	for i := 0; i < len(s); i++ {
		runes = append(runes, rune(s[i]))
	}
	return string(runes)
}

func isAllowedPathChar(r rune) bool {
	return unicode.IsLetter(r) || unicode.IsDigit(r) ||
		r == '/' || r == '-' || r == '_' || r == '.' || r == ' '
}

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

// detectFileTypeFromExt auto-detects file type based on extension
func detectFileTypeFromExt(ext string) string {
	imageExts := []string{".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"}
	videoExts := []string{".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}

	for _, e := range imageExts {
		if ext == e {
			return "image"
		}
	}
	for _, e := range videoExts {
		if ext == e {
			return "video"
		}
	}
	return "document"
}

func isValidFileType(fileType, filename string) bool {
	ext := strings.ToLower(filepath.Ext(filename))
	allowedTypes := map[string][]string{
		"video":    {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"},
		"document": {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".csv", ".zip", ".rar", ".7z", ".tar", ".gz", ".ipynb", ".py", ".cpp", ".sh", ".json", ".sql"},
		"image":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"},
	}
	if allowed, ok := allowedTypes[fileType]; ok {
		for _, a := range allowed {
			if ext == a {
				return true
			}
		}
		return false
	}
	all := []string{
		".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v",
		".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".csv", ".zip", ".rar", ".7z", ".tar", ".gz", ".ipynb", ".py", ".cpp", ".sh", ".json", ".sql",
		".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
	}
	for _, a := range all {
		if ext == a {
			return true
		}
	}
	return false
}

func getContentType(filename string) string {
	ext := strings.ToLower(filepath.Ext(filename))
	contentTypes := map[string]string{
		".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
		".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml", ".bmp": "image/bmp",
		".mp4": "video/mp4", ".webm": "video/webm", ".avi": "video/x-msvideo",
		".mov": "video/quicktime", ".mkv": "video/x-matroska",
		".m4v": "video/x-m4v", ".flv": "video/x-flv", ".wmv": "video/x-ms-wmv",
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
	if ct, ok := contentTypes[ext]; ok {
		return ct
	}
	return "application/octet-stream"
}

func isImage(ext string) bool {
	for _, e := range []string{".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"} {
		if ext == e {
			return true
		}
	}
	return false
}

func isVideo(ext string) bool {
	for _, e := range []string{".mp4", ".webm", ".avi", ".mov", ".mkv", ".m4v", ".flv", ".wmv"} {
		if ext == e {
			return true
		}
	}
	return false
}
