package handler

import (
	"context"
	"errors"
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

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"example/hello/internal/config"
	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"
	"example/hello/pkg/storage"
)

type FileHandler struct {
	storage storage.Storage
	config  config.UploadConfig
	access  fileAccess
}

func NewFileHandler(storage storage.Storage, cfg config.UploadConfig, access ...fileAccess) *FileHandler {
	var policy fileAccess
	if len(access) > 0 {
		policy = access[0]
	}
	return &FileHandler{
		storage: storage,
		config:  cfg,
		access:  policy,
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

// FileUploadBatchResponse is returned when a multipart request contains more
// than one `file` part.  Single-file callers retain the original response
// shape, while the course-blueprint workspace can upload a whole syllabus in
// one request without losing all but the last file.
type FileUploadBatchResponse struct {
	Files []FileUploadResponse `json:"files"`
}

// UploadFile godoc
// @Summary Upload a file
// @Description Upload a file to storage (video, document, or image)
// @Tags Files
// @Accept multipart/form-data
// @Produce json
// @Param file formData file true "File to upload"
// @Param type formData string false "File type (video, document, image)" default(document)
// @Param visibility formData string false "private or public; must precede file parts. Documents default private."
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=FileUploadResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /files/upload [post]
func (h *FileHandler) UploadFile(c *gin.Context) {
	if c.GetInt64("user_id") <= 0 || h.access == nil {
		c.AbortWithStatus(http.StatusServiceUnavailable)
		return
	}
	maxSize := h.config.MaxSize
	if maxSize <= 0 {
		maxSize = 100 << 20
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxSize+(1<<20))
	reader, err := c.Request.MultipartReader()
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Failed to process multipart form"))
		return
	}

	var fileType string = "document"
	public := false
	visibilitySet := false
	committed := false
	var createdPaths []string
	defer func() {
		if !committed {
			for _, key := range createdPaths {
				ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
				_ = h.storage.Delete(ctx, key)
				_ = h.access.Forget(ctx, key)
				cancel()
			}
		}
	}()
	var uploadedResponse *FileUploadResponse
	uploadedFiles := make([]FileUploadResponse, 0)

	for {
		part, err := reader.NextPart()
		if err != nil {
			if err == io.EOF {
				break
			}
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("upload_error", "Invalid or oversized multipart request"))
			return
		}

		formName := part.FormName()
		if formName == "visibility" {
			if len(uploadedFiles) > 0 {
				c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_visibility", "Visibility must precede files"))
				return
			}
			value, err := io.ReadAll(io.LimitReader(part, 16))
			part.Close()
			if err != nil || (string(value) != "public" && string(value) != "private") {
				c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_visibility", "Use public or private visibility before file parts"))
				return
			}
			public = string(value) == "public"
			visibilitySet = true
			continue
		}

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

		if len(uploadedFiles) >= 10 {
			part.Close()
			c.JSON(http.StatusRequestEntityTooLarge, dto.NewErrorResponse("too_many_files", "Maximum 10 files per request"))
			return
		}
		filename := part.FileName()
		if filename == "" {
			part.Close()
			continue
		}

		// Auto-detect file type from extension if not explicitly provided or mismatched
		ext := strings.ToLower(filepath.Ext(filename))
		effectiveType := fileType
		if effectiveType == "document" {
			// Try to auto-detect from extension
			detectedType := detectFileTypeFromExt(ext)
			if detectedType != "document" {
				effectiveType = detectedType
			}
		}

		// Validate extension
		if !isValidFileType(effectiveType, filename) {
			part.Close()
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse(
				"invalid_file_type",
				fmt.Sprintf("File type %s is not allowed for %s uploads.", ext, effectiveType),
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

		fileSize, err := io.Copy(tmpFile, io.LimitReader(part, maxSize+1))
		tmpFile.Close()

		if err != nil {
			os.Remove(tmpPath)
			logger.Error("Failed to buffer upload to temp file", err)
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to read uploaded file"))
			return
		}

		if fileSize > maxSize {
			os.Remove(tmpPath)
			c.JSON(http.StatusRequestEntityTooLarge, dto.NewErrorResponse(
				"file_too_large",
				fmt.Sprintf("File exceeds maximum size of %d MB", h.config.MaxSize/1024/1024),
			))
			return
		}

		part.Close()

		fileID := uuid.New().String()
		timestamp := time.Now().Format("20060102150405")
		ext = strings.ToLower(filepath.Ext(filename))
		cleanName := cleanFilename(filename)
		nameWithoutExt := strings.TrimSuffix(cleanName, ext)
		storedFilename := fmt.Sprintf("%s/%s_%s_%s%s", effectiveType, timestamp, fileID[:8], nameWithoutExt, ext)
		contentType := getContentType(filename)

		tmpReader, err := os.Open(tmpPath)
		if err != nil {
			os.Remove(tmpPath)
			logger.Error("Failed to re-open temp file for upload", err)
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to process file"))
			return
		}

		if (isImage(ext) && ext != ".svg") || ext == ".pdf" {
			header := make([]byte, 512)
			n, readErr := tmpReader.Read(header)
			if readErr != nil && readErr != io.EOF {
				tmpReader.Close()
				os.Remove(tmpPath)
				c.AbortWithStatus(http.StatusBadRequest)
				return
			}
			detected := http.DetectContentType(header[:n])
			if detected != contentType {
				tmpReader.Close()
				os.Remove(tmpPath)
				c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_file_content", "File content does not match its extension"))
				return
			}
			if _, err := tmpReader.Seek(0, io.SeekStart); err != nil {
				tmpReader.Close()
				os.Remove(tmpPath)
				c.AbortWithStatus(http.StatusInternalServerError)
				return
			}
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

		createdPaths = append(createdPaths, storedFilename)
		if err := h.access.Register(c.Request.Context(), storedFilename, c.GetInt64("user_id"), fileSize, public || (!visibilitySet && effectiveType == "image")); err != nil {
			if errors.Is(err, service.ErrFileQuota) {
				c.JSON(http.StatusRequestEntityTooLarge, dto.NewErrorResponse("storage_quota", "File storage quota exceeded"))
				return
			}
			logger.Error("File metadata registration failed", err)
			c.AbortWithStatus(http.StatusServiceUnavailable)
			return
		}
		uploadedResponse = &FileUploadResponse{
			FileID:   fileID,
			FileName: filename,
			FileURL:  fmt.Sprintf("/files/%s", storedFilename),
			FilePath: storedFilename,
			FileSize: fileSize,
			FileType: effectiveType,
		}
		uploadedFiles = append(uploadedFiles, *uploadedResponse)
	}

	if uploadedResponse == nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_file", "No file found in request"))
		return
	}

	committed = true
	if len(uploadedFiles) == 1 {
		c.JSON(http.StatusOK, dto.NewDataResponse(uploadedResponse))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(FileUploadBatchResponse{Files: uploadedFiles}))
}

// ServeFile godoc
// @Summary Serve an authorized file for inline viewing
// @Description Public assets are readable anonymously; private assets require owner/course access or internal service authentication.
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

	if !h.authorizeFile(c, filename, false) {
		return
	}
	// Chat attachments are private to a channel/DM. They are fetched through
	// chat-service, which checks membership for every request, never through the
	// LMS public file endpoint.
	if strings.HasPrefix(filename, "chat/") {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
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

	c.Header("Accept-Ranges", "bytes")

	ext := strings.ToLower(filepath.Ext(filename))
	// Uploaded source code, HTML/SVG and unknown binaries must download rather
	// than execute/render in the LMS origin. Preview only passive media.
	if (isImage(ext) && ext != ".svg") || isVideo(ext) || ext == ".pdf" {
		c.Header("Content-Disposition", "inline")
	} else {
		c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, filepath.Base(filename)))
	}

	c.Header("Cache-Control", "private, no-store")
	c.Header("X-Content-Type-Options", "nosniff")
	if result.ETag != "" {
		c.Header("ETag", normalizeETag(result.ETag))
	}

	contentType := result.ContentType
	if contentType == "" || contentType == "application/octet-stream" {
		contentType = getContentType(filename)
	}

	c.Writer.Header().Set("Content-Type", contentType)
	http.ServeContent(c.Writer, c.Request, filepath.Base(filename), result.LastModified, result.Body)
}

// DownloadFile godoc
// @Summary Download an authorized file as attachment
// @Description Private assets require owner/course access or internal service authentication.
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

	if !h.authorizeFile(c, filename, false) {
		return
	}
	if strings.HasPrefix(filename, "chat/") {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
		return
	}

	result, err := h.storage.GetObject(c.Request.Context(), filename)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
		return
	}
	defer result.Body.Close()

	c.Header("Cache-Control", "private, no-store")
	c.Header("X-Content-Type-Options", "nosniff")
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

	if !h.authorizeFile(c, filename, true) {
		return
	}

	if err := h.storage.Delete(c.Request.Context(), filename); err != nil {
		logger.Error(fmt.Sprintf("Failed to delete file %s", filename), err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("delete_failed", "Failed to delete file"))
		return
	}

	if err := h.access.Forget(c.Request.Context(), filename); err != nil {
		logger.Error("File metadata cleanup failed", err)
		c.AbortWithStatus(http.StatusServiceUnavailable)
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

	if !h.authorizeFile(c, filename, false) {
		return
	}
	if strings.HasPrefix(filename, "chat/") {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
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
	// Storage is format-agnostic: a course may legitimately contain source
	// code, notebooks, datasets, cluster scripts or a specialist binary. The
	// safety boundary is filename/path sanitisation and forced download for
	// unrenderable formats, not an ever-growing extension allow-list.
	if fileType != "document" && fileType != "video" && fileType != "image" {
		return false
	}
	return strings.TrimSpace(filepath.Base(filename)) != ""
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
		".json": "application/json", ".ipynb": "application/x-ipynb+json",
		".py": "text/x-python", ".cpp": "text/x-c++src", ".c": "text/x-csrc",
		".h": "text/x-chdr", ".hpp": "text/x-c++hdr", ".java": "text/x-java-source",
		".js": "text/javascript", ".ts": "text/typescript", ".tsx": "text/tsx",
		".go": "text/x-go", ".rs": "text/x-rust", ".sh": "text/x-shellscript",
		".sbatch": "text/x-shellscript", ".sql": "application/sql", ".yaml": "application/yaml", ".yml": "application/yaml",
		".zip": "application/zip", ".tar": "application/x-tar", ".gz": "application/gzip", ".7z": "application/x-7z-compressed", ".rar": "application/vnd.rar",
	}
	if ct, ok := contentTypes[ext]; ok {
		return ct
	}
	return "application/octet-stream"
}

func normalizeETag(etag string) string {
	etag = strings.TrimSpace(etag)
	if etag == "" || strings.HasPrefix(etag, `W/"`) {
		return etag
	}
	if strings.HasPrefix(etag, `"`) && strings.HasSuffix(etag, `"`) {
		return etag
	}
	return `"` + strings.Trim(etag, `"`) + `"`
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
