package dto

// ── Requests from frontend ───────────────────────────────────────────

type GenerateMicroLessonsRequest struct {
	ContentID     int64  `json:"content_id"`
	YouTubeURL    string `json:"youtube_url,omitempty"`
	SectionID     *int64 `json:"section_id,omitempty"`
	TargetMinutes int    `json:"target_minutes"`
	Language      string `json:"language"`
}

type UpdateMicroLessonRequest struct {
	Title            string   `json:"title" binding:"required"`
	Summary          string   `json:"summary"`
	Objectives       []string `json:"objectives"`
	MarkdownContent  string   `json:"markdown_content" binding:"required"`
	EstimatedMinutes int      `json:"estimated_minutes"`
	OrderIndex       int      `json:"order_index"`
}

type PublishMicroLessonRequest struct {
	SectionID  int64 `json:"section_id" binding:"required"`
	OrderIndex int   `json:"order_index"`
}

// ── Internal callback payloads (AI service -> LMS) ────────────────────

type MicroLessonStatusCallback struct {
	JobID        int64  `json:"job_id" binding:"required"`
	Status       string `json:"status" binding:"required"`
	Progress     int    `json:"progress"`
	Stage        string `json:"stage"`
	LessonsCount int    `json:"lessons_count"`
	Error        string `json:"error"`
}

type MicroLessonGeneratedItem struct {
	Title            string   `json:"title"`
	Summary          string   `json:"summary"`
	Objectives       []string `json:"objectives"`
	MarkdownContent  string   `json:"markdown_content"`
	EstimatedMinutes int      `json:"estimated_minutes"`
	ImageURLs        []string `json:"image_urls"`
	OrderIndex       int      `json:"order_index"`
	NodeID           *int64   `json:"node_id"`
}

type MicroLessonsCallback struct {
	JobID           int64                      `json:"job_id" binding:"required"`
	CourseID        int64                      `json:"course_id" binding:"required"`
	SectionID       *int64                     `json:"section_id"`
	SourceContentID *int64                     `json:"source_content_id"`
	Language        string                     `json:"language"`
	Lessons         []MicroLessonGeneratedItem `json:"lessons" binding:"required"`
}