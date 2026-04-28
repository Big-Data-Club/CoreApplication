// lms-service/pkg/ai/client.go
// HTTP client for calling the Python ai-service.
// All AI features route through this client.
package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"example/hello/pkg/logger"
)

// Client is the HTTP client for the ai-service.
type Client struct {
	baseURL    string
	secret     string
	httpClient *http.Client
}

// NewClient creates a new ai-service client.
// baseURL example: "http://ai-service:8000"
func NewClient() *Client {
	baseURL := getEnvOrDefault("AI_SERVICE_URL", "http://ai-service:8000")
	secret := getEnvOrDefault("AI_SERVICE_SECRET", "ai-service-secret-change-me")
	return &Client{
		baseURL: baseURL,
		secret:  secret,
		httpClient: &http.Client{
			Timeout: 600 * time.Second, // quiz gen can take 6+ LLM calls (~60s each)
		},
	}
}

// ── Process Document ──────────────────────────────────────────────────────────

// ProcessDocumentRequest triggers document ingestion in the ai-service.
type ProcessDocumentRequest struct {
	ContentID   int64   `json:"content_id"`
	CourseID    int64   `json:"course_id"`
	NodeID      *int64  `json:"node_id,omitempty"`
	FileURL     string  `json:"file_url"`
	ContentType string  `json:"content_type"`
}

type ProcessDocumentResponse struct {
	JobID   int    `json:"job_id"`
	Status  string `json:"status"`
	Message string `json:"message"`
}

func (c *Client) ProcessDocument(ctx context.Context, req ProcessDocumentRequest) (*ProcessDocumentResponse, error) {
	var resp ProcessDocumentResponse
	if err := c.post(ctx, "/ai/process-document", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.ProcessDocument: %w", err)
	}
	return &resp, nil
}

// ── Error Diagnosis (Phase 1) ─────────────────────────────────────────────────

// DiagnoseRequest is sent to the ai-service when a student answers incorrectly.
type DiagnoseRequest struct {
	StudentID   int64  `json:"student_id"`
	AttemptID   int64  `json:"attempt_id"`
	QuestionID  int64  `json:"question_id"`
	WrongAnswer string `json:"wrong_answer"`
	CourseID    int64  `json:"course_id"`
	// Enrichment fields — LMS provides these so AI doesn't query LMS DB
	QuestionText  string                   `json:"question_text"`
	QuestionType  string                   `json:"question_type"`
	Explanation   string                   `json:"explanation"`
	CorrectAnswer string                   `json:"correct_answer"`
	AnswerOptions []map[string]interface{} `json:"answer_options"`
	NodeID        *int64                   `json:"node_id,omitempty"`
}

// DiagnoseResponse contains LLM explanation + deep link.
type DiagnoseResponse struct {
	Explanation     string                 `json:"explanation"`
	GapType         string                   `json:"gap_type"`
	KnowledgeGap    string                   `json:"knowledge_gap"`
	StudySuggestion string                   `json:"study_suggestion"`
	Confidence      float64                  `json:"confidence"`
	SourceChunkID   *int64                   `json:"source_chunk_id"`
	SuggestedDocuments []map[string]interface{} `json:"suggested_documents"`
	Language        string                   `json:"language"`
}

type ChunkItem struct {
    ID           int64   `json:"id"`
    ChunkText    string  `json:"chunk_text"`
    ChunkIndex   int     `json:"chunk_index"`
    SourceType   string  `json:"source_type"`
    PageNumber   *int    `json:"page_number"`
    StartTimeSec *int    `json:"start_time_sec"`
    EndTimeSec   *int    `json:"end_time_sec"`
    Language     string  `json:"language"`
}

func (c *Client) DiagnoseError(ctx context.Context, req DiagnoseRequest) (*DiagnoseResponse, error) {
	var resp DiagnoseResponse
	if err := c.post(ctx, "/ai/diagnose", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.DiagnoseError: %w", err)
	}
	return &resp, nil
}

// ── Heatmap ───────────────────────────────────────────────────────────────────

type HeatmapNode struct {
	NodeID       int64   `json:"node_id"`
	NodeName     string  `json:"node_name"`
	NodeNameVI   string  `json:"name_vi"`
	StudentCount int     `json:"student_count"`
	AvgMastery   float64 `json:"avg_mastery"`
	TotalWrong   int     `json:"total_wrong"`
	TotalAttempts int    `json:"total_attempts"`
	WrongRate    float64 `json:"wrong_rate"`
}

func (c *Client) GetClassHeatmap(ctx context.Context, courseID int64) ([]HeatmapNode, error) {
	var resp []HeatmapNode
	if err := c.get(ctx, fmt.Sprintf("/ai/diagnose/heatmap/class/%d", courseID), &resp); err != nil {
		return nil, fmt.Errorf("ai.GetClassHeatmap: %w", err)
	}
	return resp, nil
}

func (c *Client) GetStudentHeatmap(ctx context.Context, studentID, courseID int64) ([]map[string]interface{}, error) {
	var resp []map[string]interface{}
	path := fmt.Sprintf("/ai/diagnose/heatmap/student/%d/course/%d", studentID, courseID)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetStudentHeatmap: %w", err)
	}
	return resp, nil
}

// ── Quiz Generation (Phase 2) ─────────────────────────────────────────────────

type GenerateQuizRequest struct {
	NodeID              int64    `json:"node_id"`
	CourseID            int64    `json:"course_id"`
	CreatedBy           int64    `json:"created_by"`
	BloomLevels         []string `json:"bloom_levels,omitempty"`
	Language            string   `json:"language"`
	QuestionsPerLevel   int      `json:"questions_per_level"`
}

type GenerateQuizResponse struct {
	Generated int    `json:"generated"`
	GenIDs    []int  `json:"gen_ids"`
	Status    string `json:"status"`
	Message   string `json:"message"`
}

func (c *Client) GenerateQuiz(ctx context.Context, req GenerateQuizRequest) (*GenerateQuizResponse, error) {
	var resp GenerateQuizResponse
	if err := c.post(ctx, "/ai/quiz/generate", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.GenerateQuiz: %w", err)
	}
	return &resp, nil
}

func (c *Client) GetDraftQuestions(ctx context.Context, courseID int64, nodeID *int64) ([]map[string]interface{}, error) {
	var resp []map[string]interface{}
	path := fmt.Sprintf("/ai/quiz/drafts/%d", courseID)
	if nodeID != nil {
		path += fmt.Sprintf("?node_id=%d", *nodeID)
	}
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetDraftQuestions: %w", err)
	}
	return resp, nil
}

type ApproveQuestionRequest struct {
	ReviewerID int64  `json:"reviewer_id"`
	QuizID     int64  `json:"quiz_id"`
	ReviewNote string `json:"review_note"`
}

// ApproveQuestionResponse is the structured response from the AI service
// containing the full question data that LMS needs to insert into quiz_questions.
type ApproveQuestionResponse struct {
	GenID          int64                    `json:"gen_id"`
	QuizID         int64                    `json:"quiz_id"`
	QuestionText   string                   `json:"question_text"`
	QuestionType   string                   `json:"question_type"`
	Explanation    string                   `json:"explanation"`
	AnswerOptions  []map[string]interface{} `json:"answer_options"`
	NodeID         *int64                   `json:"node_id"`
	BloomLevel     string                   `json:"bloom_level"`
	SourceChunkID  *int64                   `json:"source_chunk_id"`
	Language       string                   `json:"language"`
}

func (c *Client) ApproveQuestion(ctx context.Context, genID int64, req ApproveQuestionRequest) (*ApproveQuestionResponse, error) {
	var resp ApproveQuestionResponse
	if err := c.post(ctx, fmt.Sprintf("/ai/quiz/%d/approve", genID), req, &resp); err != nil {
		return nil, fmt.Errorf("ai.ApproveQuestion: %w", err)
	}
	return &resp, nil
}

// PublishQuestion notifies AI that LMS has successfully created the quiz_question.
func (c *Client) PublishQuestion(ctx context.Context, genID int64, quizQuestionID int64) error {
	var resp map[string]interface{}
	body := map[string]int64{"quiz_question_id": quizQuestionID}
	return c.post(ctx, fmt.Sprintf("/ai/quiz/%d/publish", genID), body, &resp)
}

type RejectQuestionRequest struct {
	ReviewerID int64  `json:"reviewer_id"`
	ReviewNote string `json:"review_note"`
}

func (c *Client) RejectQuestion(ctx context.Context, genID int64, req RejectQuestionRequest) error {
	var resp map[string]interface{}
	return c.post(ctx, fmt.Sprintf("/ai/quiz/%d/reject", genID), req, &resp)
}

// ── Spaced Repetition (Phase 2) ────────────────────────────────────────────────

type RecordReviewRequest struct {
	StudentID  int64  `json:"student_id"`
	QuestionID int64  `json:"question_id"`
	CourseID   int64  `json:"course_id"`
	NodeID     *int64 `json:"node_id,omitempty"`
	Quality    int    `json:"quality"` // 0-5
}

func (c *Client) RecordReviewResponse(ctx context.Context, req RecordReviewRequest) (map[string]interface{}, error) {
	var resp map[string]interface{}
	if err := c.post(ctx, "/ai/spaced-repetition/record", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.RecordReviewResponse: %w", err)
	}
	return resp, nil
}

func (c *Client) GetDueReviews(ctx context.Context, studentID, courseID int64, limit int) ([]map[string]interface{}, error) {
	var resp []map[string]interface{}
	path := fmt.Sprintf("/ai/spaced-repetition/due/student/%d/course/%d?limit=%d", studentID, courseID, limit)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetDueReviews: %w", err)
	}
	return resp, nil
}

func (c *Client) GetReviewStats(ctx context.Context, studentID, courseID int64) (map[string]interface{}, error) {
	var resp map[string]interface{}
	path := fmt.Sprintf("/ai/spaced-repetition/stats/student/%d/course/%d", studentID, courseID)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetReviewStats: %w", err)
	}
	return resp, nil
}

// ── Knowledge Nodes ────────────────────────────────────────────────────────────

type GenerateFlashcardsRequest struct {
	StudentID      int64    `json:"student_id"`
	NodeID         int64    `json:"node_id"`
	CourseID       int64    `json:"course_id"`
	Count          int      `json:"count"`
	ExistingFronts []string `json:"existing_fronts,omitempty"`
}

type AIFlashcard struct {
	ID        int64     `json:"id"`
	CourseID  int64     `json:"course_id"`
	NodeID    int64     `json:"node_id"`
	FrontText string    `json:"front_text"`
	BackText  string    `json:"back_text"`
	Status    string    `json:"status"`
	CreatedAt string    `json:"created_at"`
}

type GenerateFlashcardsResponse struct {
	Flashcards []AIFlashcard `json:"flashcards"`
}

func (c *Client) GenerateFlashcards(ctx context.Context, req GenerateFlashcardsRequest) (*GenerateFlashcardsResponse, error) {
	var resp GenerateFlashcardsResponse
	if err := c.post(ctx, "/ai/flashcards/generate", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.GenerateFlashcards: %w", err)
	}
	return &resp, nil
}

func (c *Client) GetDueFlashcards(ctx context.Context, studentID, courseID int64) ([]map[string]interface{}, error) {
	var resp []map[string]interface{}
	path := fmt.Sprintf("/ai/flashcards/due/student/%d/course/%d", studentID, courseID)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetDueFlashcards: %w", err)
	}
	return resp, nil
}

func (c *Client) GetNodeFlashcards(ctx context.Context, nodeID, courseID, studentID int64) ([]map[string]interface{}, error) {
	var resp []map[string]interface{}
	path := fmt.Sprintf("/ai/flashcards/node/%d/course/%d/student/%d", nodeID, courseID, studentID)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetNodeFlashcards: %w", err)
	}
	return resp, nil
}

type ReviewFlashcardRequest struct {
	StudentID   int64 `json:"student_id"`
	FlashcardID int64 `json:"flashcard_id"`
	Quality     int   `json:"quality"`
}

func (c *Client) ReviewFlashcard(ctx context.Context, req ReviewFlashcardRequest) (map[string]interface{}, error) {
	var resp map[string]interface{}
	if err := c.post(ctx, "/ai/flashcards/review", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.ReviewFlashcard: %w", err)
	}
	return resp, nil
}

// ── Knowledge Nodes ────────────────────────────────────────────────────────────

type CreateNodeRequest struct {
	CourseID    int64   `json:"course_id"`
	Name        string  `json:"name"`
	NameVI      string  `json:"name_vi,omitempty"`
	NameEN      string  `json:"name_en,omitempty"`
	Description string  `json:"description,omitempty"`
	ParentID    *int64  `json:"parent_id,omitempty"`
	OrderIndex  int     `json:"order_index"`
}

func (c *Client) CreateKnowledgeNode(ctx context.Context, req CreateNodeRequest) (map[string]interface{}, error) {
	var resp map[string]interface{}
	if err := c.post(ctx, "/ai/knowledge-nodes", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.CreateKnowledgeNode: %w", err)
	}
	return resp, nil
}

func (c *Client) ListKnowledgeNodes(ctx context.Context, courseID int64) ([]map[string]interface{}, error) {
	var resp []map[string]interface{}
	if err := c.get(ctx, fmt.Sprintf("/ai/knowledge-nodes/course/%d", courseID), &resp); err != nil {
		return nil, fmt.Errorf("ai.ListKnowledgeNodes: %w", err)
	}
	return resp, nil
}

// AutoIndexRequest triggers auto-indexing for a content item.
type AutoIndexRequest struct {
	ContentID   int64  `json:"content_id"`
	CourseID    int64  `json:"course_id"`
	FileURL     string `json:"file_url"`
	ContentType string `json:"content_type"`
}

// AutoIndexTextRequest triggers auto-indexing for TEXT content.
type AutoIndexTextRequest struct {
	ContentID   int64  `json:"content_id"`
	CourseID    int64  `json:"course_id"`
	Title       string `json:"title"`
	TextContent string `json:"text_content"`
}
 
type AutoIndexResponse struct {
	JobID     string `json:"job_id"`
	ContentID int64  `json:"content_id"`
	Status    string `json:"status"`
	Message   string `json:"message"`
}
 
type AutoIndexStatus struct {
	ContentID    int64  `json:"content_id"`
	Status       string `json:"status"` // queued|processing|indexed|failed
	NodesCreated int    `json:"nodes_created"`
	ChunksCreated int   `json:"chunks_created"`
	Error        string `json:"error,omitempty"`
}

type WeaknessNode struct {
	NodeID       int64   `json:"node_id"`
	NodeName     string  `json:"node_name"`
	NameVI       string  `json:"name_vi"`
	WrongCount   int     `json:"wrong_count"`
	TotalAttempt int     `json:"total_attempts"`
	MasteryLevel float64 `json:"mastery_level"`
	StatusLevel    string  `json:"status_level"`
	FlashcardCount int     `json:"flashcard_count"`
}

// AutoIndex triggers the auto-index pipeline for file content.
func (c *Client) AutoIndex(ctx context.Context, req AutoIndexRequest) (*AutoIndexResponse, error) {
	var resp AutoIndexResponse
	if err := c.post(ctx, "/ai/auto-index", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.AutoIndex: %w", err)
	}
	return &resp, nil
}

// AutoIndexText triggers auto-indexing for TEXT content.
func (c *Client) AutoIndexText(ctx context.Context, req AutoIndexTextRequest) (*AutoIndexResponse, error) {
	var resp AutoIndexResponse
	if err := c.post(ctx, "/ai/auto-index/text", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.AutoIndexText: %w", err)
	}
	return &resp, nil
}
 
// GetAutoIndexStatus polls the auto-index job status.
func (c *Client) GetAutoIndexStatus(ctx context.Context, contentID int64) (*AutoIndexStatus, error) {
	var resp AutoIndexStatus
	path := fmt.Sprintf("/ai/auto-index/%d/status", contentID)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetAutoIndexStatus: %w", err)
	}
	return &resp, nil
}

// BatchGetAutoIndexStatus fetches index status for multiple content IDs
// in a single round-trip. Returns a map keyed by content_id string.
func (c *Client) BatchGetAutoIndexStatus(ctx context.Context, contentIDs []int64) (map[string]*AutoIndexStatus, error) {
	body := map[string][]int64{"content_ids": contentIDs}
	var resp map[string]*AutoIndexStatus
	if err := c.post(ctx, "/ai/auto-index/batch-status", body, &resp); err != nil {
		return nil, fmt.Errorf("ai.BatchGetAutoIndexStatus: %w", err)
	}
	return resp, nil
}

func (c *Client) GetNodeChunks(ctx context.Context, nodeID int64, limit int) ([]ChunkItem, error) {
    var resp []ChunkItem
    return resp, c.get(ctx, fmt.Sprintf("/ai/knowledge-nodes/%d/chunks?limit=%d", nodeID, limit), &resp)
}
 
// KnowledgeGraphNode represents a node in the knowledge graph.
type KnowledgeGraphNode struct {
	ID                 int64   `json:"id"`
	Name               string  `json:"name"`
	NameVI             string  `json:"name_vi"`
	NameEN             string  `json:"name_en"`
	Description        string  `json:"description"`
	SourceContentID    *int64  `json:"source_content_id"`
	SourceContentTitle string  `json:"source_content_title"`
	CourseID           *int64  `json:"course_id"`
	AutoGenerated      bool    `json:"auto_generated"`
	ChunkCount         int     `json:"chunk_count"`
	Level              int     `json:"level"`
}
 
// KnowledgeGraphEdge represents a directed edge in the knowledge graph.
type KnowledgeGraphEdge struct {
	Source       int64   `json:"source"`
	Target       int64   `json:"target"`
	RelationType string  `json:"relation_type"`
	Strength     float64 `json:"strength"`
	AutoGenerated bool   `json:"auto_generated"`
}
 
type KnowledgeGraphResponse struct {
	CourseID int64                `json:"course_id"`
	Nodes    []KnowledgeGraphNode `json:"nodes"`
	Edges    []KnowledgeGraphEdge `json:"edges"`
}
 
// GetKnowledgeGraph returns the full knowledge graph for a course.
func (c *Client) GetKnowledgeGraph(ctx context.Context, courseID int64) (*KnowledgeGraphResponse, error) {
	var resp KnowledgeGraphResponse
	if err := c.get(ctx, fmt.Sprintf("/ai/knowledge-graph/%d", courseID), &resp); err != nil {
		return nil, fmt.Errorf("ai.GetKnowledgeGraph: %w", err)
	}
	return &resp, nil
}

// GetGlobalKnowledgeGraph returns the full knowledge graph across all courses.
func (c *Client) GetGlobalKnowledgeGraph(ctx context.Context, minStrength float64, limit int) (*KnowledgeGraphResponse, error) {
	var resp KnowledgeGraphResponse
	path := fmt.Sprintf("/ai/knowledge-graph/global?min_strength=%f&limit=%d", minStrength, limit)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.GetGlobalKnowledgeGraph: %w", err)
	}
	return &resp, nil
}

// ── Micro-Lessons ─────────────────────────────────────────────────────────────

// GenerateMicroLessonsRequest tells the AI service to start generating
// bite-sized lessons for an already-uploaded source file.
type GenerateMicroLessonsRequest struct {
	JobID           int64  `json:"job_id"`
	CourseID        int64  `json:"course_id"`
	SectionID       *int64 `json:"section_id,omitempty"`
	SourceContentID *int64 `json:"source_content_id,omitempty"`
	SourceFilePath  string `json:"source_file_path"`
	SourceFileType  string `json:"source_file_type,omitempty"`
	TargetMinutes   int    `json:"target_minutes"`
	Language        string `json:"language"`
}

type GenerateMicroLessonsFromYouTubeRequest struct {
	JobID           int64  `json:"job_id"`
	CourseID        int64  `json:"course_id"`
	SectionID       *int64 `json:"section_id,omitempty"`
	SourceContentID *int64 `json:"source_content_id,omitempty"`
	YouTubeURL      string `json:"youtube_url"`
	TargetMinutes   int    `json:"target_minutes"`
	Language        string `json:"language"`
}

type GenerateMicroLessonsResponse struct {
	JobID  int64  `json:"job_id"`
	Status string `json:"status"`
}

// GenerateMicroLessons fires the file-based micro-lesson pipeline.
func (c *Client) GenerateMicroLessons(ctx context.Context, req GenerateMicroLessonsRequest) (*GenerateMicroLessonsResponse, error) {
	var resp GenerateMicroLessonsResponse
	if err := c.post(ctx, "/ai/micro-lessons/generate", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.GenerateMicroLessons: %w", err)
	}
	return &resp, nil
}

// GenerateMicroLessonsFromYouTube fires the YouTube transcript micro-lesson pipeline.
func (c *Client) GenerateMicroLessonsFromYouTube(ctx context.Context, req GenerateMicroLessonsFromYouTubeRequest) (*GenerateMicroLessonsResponse, error) {
	var resp GenerateMicroLessonsResponse
	if err := c.post(ctx, "/ai/micro-lessons/generate-youtube", req, &resp); err != nil {
		return nil, fmt.Errorf("ai.GenerateMicroLessonsFromYouTube: %w", err)
	}
	return &resp, nil
}

// LinkGlobalGraph triggers a system-wide knowledge graph maintenance task via Kafka command.
func (c *Client) LinkGlobalGraph(ctx context.Context) (map[string]interface{}, error) {
	var resp map[string]interface{}
	if err := c.post(ctx, "/ai/knowledge-graph/link-global", nil, &resp); err != nil {
		return nil, fmt.Errorf("ai.LinkGlobalGraph: %w", err)
	}
	return resp, nil
}

// PreviewGraphConsolidation returns the dry-run merge plan for a course.
func (c *Client) PreviewGraphConsolidation(ctx context.Context, courseID int64) (map[string]interface{}, error) {
	var resp map[string]interface{}
	path := fmt.Sprintf("/ai/knowledge-graph/%d/consolidate/preview", courseID)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, fmt.Errorf("ai.PreviewGraphConsolidation: %w", err)
	}
	return resp, nil
}

// TriggerGraphConsolidation enqueues a "Compact Graph" Kafka command for a course.
func (c *Client) TriggerGraphConsolidation(ctx context.Context, courseID int64, triggeredBy int64) (map[string]interface{}, error) {
	body := map[string]interface{}{"triggered_by": triggeredBy}
	var resp map[string]interface{}
	path := fmt.Sprintf("/ai/knowledge-graph/%d/consolidate", courseID)
	if err := c.post(ctx, path, body, &resp); err != nil {
		return nil, fmt.Errorf("ai.TriggerGraphConsolidation: %w", err)
	}
	return resp, nil
}
 
// DeleteKnowledgeNode removes an auto-generated node.
func (c *Client) DeleteKnowledgeNode(ctx context.Context, nodeID int64) error {
	var resp map[string]interface{}
	return c.delete(ctx, fmt.Sprintf("/ai/knowledge-graph/node/%d", nodeID), &resp)
}

func (c *Client) delete(ctx context.Context, path string, result interface{}) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, c.baseURL+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("X-AI-Secret", c.secret)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("ai-service DELETE %s: %w", path, err)
	}
	defer resp.Body.Close()

	return c.decodeResponse(resp, path, result)
}

// GetStudentWeaknesses calls the AI service heatmap endpoint and transforms
// the response into weakness nodes with status labels.
// AI service owns student_knowledge_progress — LMS never queries it directly.
func (c *Client) GetStudentWeaknesses(ctx context.Context, studentID, courseID int64) ([]WeaknessNode, error) {
	raw, err := c.GetStudentHeatmap(ctx, studentID, courseID)
	if err != nil {
		return nil, fmt.Errorf("ai.GetStudentWeaknesses: %w", err)
	}
 
	nodes := make([]WeaknessNode, 0, len(raw))
	for _, r := range raw {
		mastery := GetFloatField(r, "mastery_level")
		wrongCount := GetIntField(r, "wrong_count")
		totalAttempt := GetIntField(r, "total_attempts")
		nodeID := GetInt64Field(r, "node_id")
		flashcardCount := GetIntField(r, "flashcard_count")
		fmt.Println("flashcardCount", flashcardCount)

		// Map mastery_level to Vietnamese status label
		statusLevel := "Rất tốt"
		switch {
		case mastery < 0.4:
			statusLevel = "Cần cải thiện"
		case mastery < 0.6:
			statusLevel = "Yếu"
		case mastery < 0.8:
			statusLevel = "TB"
		}
 
		nodes = append(nodes, WeaknessNode{
			NodeID:         nodeID,
			NodeName:       GetStringField(r, "node_name"),
			NameVI:         GetStringField(r, "name_vi"),
			WrongCount:     wrongCount,
			TotalAttempt:   totalAttempt,
			MasteryLevel:   mastery,
			StatusLevel:    statusLevel,
			FlashcardCount: flashcardCount,
		})
	}
	return nodes, nil
}
 
// GetIntField safely extracts an int from map[string]interface{}
func GetIntField(m map[string]interface{}, key string) int {
	if v, ok := m[key]; ok {
		switch tv := v.(type) {
		case float64:
			return int(tv)
		case int:
			return tv
		case int64:
			return int(tv)
		}
	}
	return 0
}

// GetInt64Field safely extracts an int64 from map[string]interface{}
func GetInt64Field(m map[string]interface{}, key string) int64 {
	if v, ok := m[key]; ok {
		switch tv := v.(type) {
		case float64:
			return int64(tv)
		case int:
			return int64(tv)
		case int64:
			return tv
		}
	}
	return 0
}

// GetFloatField safely extracts a float64 from map[string]interface{}
func GetFloatField(m map[string]interface{}, key string) float64 {
	if v, ok := m[key].(float64); ok {
		return v
	}
	return 0
}

// GetStringField safely extracts a string from a map[string]interface{}
func GetStringField(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

func (c *Client) post(ctx context.Context, path string, body, result interface{}) error {
	b, err := json.Marshal(body)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(b))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-AI-Secret", c.secret)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("ai-service POST %s: %w", path, err)
	}
	defer resp.Body.Close()

	return c.decodeResponse(resp, path, result)
}

func (c *Client) get(ctx context.Context, path string, result interface{}) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("X-AI-Secret", c.secret)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("ai-service GET %s: %w", path, err)
	}
	defer resp.Body.Close()

	return c.decodeResponse(resp, path, result)
}

func (c *Client) decodeResponse(resp *http.Response, path string, result interface{}) error {
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	if resp.StatusCode >= 400 {
		logger.Error(fmt.Sprintf("ai-service %s → %d: %s", path, resp.StatusCode, string(body)), nil)
		return fmt.Errorf("ai-service error %d: %s", resp.StatusCode, string(body))
	}

	if result != nil {
		return json.Unmarshal(body, result)
	}
	return nil
}

func getEnvOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}