// lms-service/internal/service/question_bank_service.go
package service

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/ai"
	"example/hello/pkg/logger"
)

// QuestionBankService - business logic for the per-course question library.
type QuestionBankService struct {
	bankRepo   *repository.QuestionBankRepository
	quizRepo   *repository.QuizRepository
	courseRepo *repository.CourseRepository
	aiClient   *ai.Client
}

func NewQuestionBankService(
	bankRepo *repository.QuestionBankRepository,
	quizRepo *repository.QuizRepository,
	courseRepo *repository.CourseRepository,
	aiClient *ai.Client,
) *QuestionBankService {
	return &QuestionBankService{bankRepo: bankRepo, quizRepo: quizRepo, courseRepo: courseRepo, aiClient: aiClient}
}

// ── Access control ────────────────────────────────────────────────────────────

func (s *QuestionBankService) verifyCourseEditAccess(ctx context.Context, courseID, userID int64, userRole string) error {
	if userRole == "ADMIN" {
		return nil
	}
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return fmt.Errorf("course not found")
	}
	if course.CreatedBy == userID {
		return nil
	}
	isCo, err := s.courseRepo.IsCoTeacher(ctx, courseID, userID)
	if err != nil {
		return err
	}
	if !isCo {
		return fmt.Errorf("permission denied: not a teacher of this course")
	}
	return nil
}

// ── Validation ────────────────────────────────────────────────────────────────

var bankValidDifficulties = map[string]bool{
	models.DifficultyEasy: true, models.DifficultyMedium: true, models.DifficultyHard: true,
}

var bankValidBlooms = map[string]bool{
	"remember": true, "understand": true, "apply": true,
	"analyze": true, "evaluate": true, "create": true,
}

var bankValidSources = map[string]bool{
	models.BankSourceManual: true, models.BankSourceImport: true, models.BankSourceAIGenerated: true,
}

func normalizeBankItem(req *dto.CreateBankItemRequest, createdBy int64) (*models.QuestionBankItem, error) {
	qType := strings.ToUpper(string(req.QuestionType))
	switch qType {
	case models.QuestionTypeSingleChoice, models.QuestionTypeMultipleChoice,
		models.QuestionTypeShortAnswer, models.QuestionTypeEssay,
		models.QuestionTypeFileUpload, models.QuestionTypeFillBlankText,
		models.QuestionTypeFillBlankDropdown:
	default:
		return nil, fmt.Errorf("invalid question_type %q", req.QuestionType)
	}

	difficulty := strings.ToUpper(strings.TrimSpace(req.Difficulty))
	if difficulty == "" {
		difficulty = models.DifficultyMedium
	}
	if !bankValidDifficulties[difficulty] {
		return nil, fmt.Errorf("invalid difficulty %q", req.Difficulty)
	}

	bloom := strings.ToLower(strings.TrimSpace(req.BloomLevel))
	if bloom != "" && !bankValidBlooms[bloom] {
		return nil, fmt.Errorf("invalid bloom_level %q", bloom)
	}

	source := strings.ToUpper(strings.TrimSpace(req.Source))
	if source == "" {
		source = models.BankSourceManual
	}
	if !bankValidSources[source] {
		return nil, fmt.Errorf("invalid source %q", source)
	}

	status := strings.ToUpper(strings.TrimSpace(req.Status))
	if status == "" {
		status = models.BankStatusApproved
	}
	if status != models.BankStatusDraft && status != models.BankStatusApproved && status != models.BankStatusDisabled {
		return nil, fmt.Errorf("invalid status %q", status)
	}

	points := 10.0
	if req.Points != nil && *req.Points >= 0 {
		points = *req.Points
	}

	answerOptions := req.AnswerOptions
	if answerOptions == nil {
		answerOptions = []dto.CreateAnswerOptionRequest{}
	}
	optionsJSON, err := json.Marshal(answerOptions)
	if err != nil {
		return nil, fmt.Errorf("invalid answer_options: %w", err)
	}
	correctAnswers := req.CorrectAnswers
	if correctAnswers == nil {
		correctAnswers = []dto.CreateCorrectAnswerRequest{}
	}
	correctJSON, err := json.Marshal(correctAnswers)
	if err != nil {
		return nil, fmt.Errorf("invalid correct_answers: %w", err)
	}
	settings := req.Settings
	if settings == nil {
		settings = map[string]interface{}{}
	}
	settingsJSON, err := repository.MarshalJSONField(settings)
	if err != nil {
		return nil, fmt.Errorf("invalid settings: %w", err)
	}

	tags := req.Tags
	if tags == nil {
		tags = []string{}
	}

	item := &models.QuestionBankItem{
		NodeID:         toNullInt64(req.NodeID),
		QuestionType:   qType,
		QuestionText:   strings.TrimSpace(req.QuestionText),
		Points:         points,
		Difficulty:     difficulty,
		AnswerOptions:  optionsJSON,
		CorrectAnswers: correctJSON,
		Settings:       settingsJSON,
		Tags:           tags,
		Source:         source,
		Status:         status,
		CreatedBy:      createdBy,
	}
	if strings.TrimSpace(req.Explanation) != "" {
		item.Explanation = toNullString(strings.TrimSpace(req.Explanation))
	}
	if bloom != "" {
		item.BloomLevel = toNullString(bloom)
	}
	return item, nil
}

// ── Public API ────────────────────────────────────────────────────────────────

func (s *QuestionBankService) CreateItems(
	ctx context.Context, courseID, userID int64, userRole string,
	req *dto.CreateBankItemsRequest,
) ([]*dto.BankItemResponse, error) {
	if err := s.verifyCourseEditAccess(ctx, courseID, userID, userRole); err != nil {
		return nil, err
	}

	items := make([]*models.QuestionBankItem, 0, len(req.Items))
	for i := range req.Items {
		item, err := normalizeBankItem(&req.Items[i], userID)
		if err != nil {
			return nil, fmt.Errorf("item %d: %w", i+1, err)
		}
		item.CourseID = courseID
		items = append(items, item)
	}

	out := make([]*dto.BankItemResponse, 0, len(items))
	for _, item := range items {
		id, err := s.bankRepo.Create(ctx, item)
		if err != nil {
			logger.Error("bank create failed", err)
			return nil, fmt.Errorf("failed to save item: %w", err)
		}
		saved, err := s.bankRepo.GetByID(ctx, id)
		if err != nil {
			return nil, err
		}
		out = append(out, ToBankItemResponse(saved))
	}
	return out, nil
}

func (s *QuestionBankService) ListItems(
	ctx context.Context, courseID, userID int64, userRole string,
	query dto.BankListQuery,
) (*dto.BankListResponse, error) {
	if err := s.verifyCourseEditAccess(ctx, courseID, userID, userRole); err != nil {
		return nil, err
	}
	if err := s.bankRepo.SyncMissingQuizQuestions(ctx, courseID); err != nil {
		return nil, fmt.Errorf("failed to reconcile quiz questions into bank: %w", err)
	}
	limit, offset := query.GetPagination()
	if query.Page < 1 {
		query.Page = 1
	}
	items, total, err := s.bankRepo.List(ctx, courseID, query, limit, offset)
	if err != nil {
		return nil, err
	}
	resp := &dto.BankListResponse{
		Items: make([]dto.BankItemResponse, 0, len(items)),
		Page:  query.Page, PageSize: limit, Total: total,
	}
	if limit > 0 {
		resp.TotalPages = int((total + int64(limit) - 1) / int64(limit))
	}
	for _, item := range items {
		resp.Items = append(resp.Items, *ToBankItemResponse(item))
	}
	return resp, nil
}

func (s *QuestionBankService) Stats(ctx context.Context, courseID, userID int64, userRole string) (*dto.BankStatsResponse, error) {
	if err := s.verifyCourseEditAccess(ctx, courseID, userID, userRole); err != nil {
		return nil, err
	}
	if err := s.bankRepo.SyncMissingQuizQuestions(ctx, courseID); err != nil {
		return nil, fmt.Errorf("failed to reconcile quiz questions into bank: %w", err)
	}
	return s.bankRepo.Stats(ctx, courseID)
}

func (s *QuestionBankService) UpdateItem(
	ctx context.Context, itemID, userID int64, userRole string,
	req *dto.UpdateBankItemRequest,
) (*dto.BankItemResponse, error) {
	existing, err := s.bankRepo.GetByID(ctx, itemID)
	if err != nil {
		return nil, err
	}
	if err := s.verifyCourseEditAccess(ctx, existing.CourseID, userID, userRole); err != nil {
		return nil, err
	}
	if req.Difficulty != "" && !bankValidDifficulties[strings.ToUpper(req.Difficulty)] {
		return nil, fmt.Errorf("invalid difficulty %q", req.Difficulty)
	}
	if req.QuestionText != nil {
		text := strings.TrimSpace(*req.QuestionText)
		if len([]rune(text)) < 3 || len([]rune(text)) > 10000 {
			return nil, fmt.Errorf("question_text must be between 3 and 10000 characters")
		}
		req.QuestionText = &text
	}
	if err := validateBankJSONArray(req.AnswerOptions, "answer_options"); err != nil {
		return nil, err
	}
	if err := validateBankJSONArray(req.CorrectAnswers, "correct_answers"); err != nil {
		return nil, err
	}
	if req.BloomLevel != nil && *req.BloomLevel != "" {
		b := strings.ToLower(strings.TrimSpace(*req.BloomLevel))
		if !bankValidBlooms[b] {
			return nil, fmt.Errorf("invalid bloom_level %q", *req.BloomLevel)
		}
		req.BloomLevel = &b
	}
	if req.Status != nil {
		st := strings.ToUpper(*req.Status)
		if st != models.BankStatusDraft && st != models.BankStatusApproved && st != models.BankStatusDisabled {
			return nil, fmt.Errorf("invalid status %q", *req.Status)
		}
		req.Status = &st
	}
	if req.Difficulty != "" {
		req.Difficulty = strings.ToUpper(req.Difficulty)
	}
	item, err := s.bankRepo.Update(ctx, itemID, *req)
	if err != nil {
		return nil, err
	}
	return ToBankItemResponse(item), nil
}

func validateBankJSONArray(raw *json.RawMessage, field string) error {
	if raw == nil {
		return nil
	}
	var values []json.RawMessage
	if !json.Valid(*raw) || json.Unmarshal(*raw, &values) != nil {
		return fmt.Errorf("%s must be a valid JSON array", field)
	}
	if len(values) > 50 {
		return fmt.Errorf("%s has too many entries", field)
	}
	return nil
}

func (s *QuestionBankService) DeleteItem(ctx context.Context, itemID, userID int64, userRole string) error {
	existing, err := s.bankRepo.GetByID(ctx, itemID)
	if err != nil {
		return err
	}
	if err := s.verifyCourseEditAccess(ctx, existing.CourseID, userID, userRole); err != nil {
		return err
	}
	return s.bankRepo.Delete(ctx, itemID)
}

func (s *QuestionBankService) SuggestQuizMetadata(
	ctx context.Context, courseID, userID int64, userRole string,
	req *dto.SuggestQuizMetadataRequest,
) (*dto.SuggestQuizMetadataResponse, error) {
	if err := s.verifyCourseEditAccess(ctx, courseID, userID, userRole); err != nil {
		return nil, err
	}
	items, err := s.bankRepo.GetByIDs(ctx, req.ItemIDs)
	if err != nil || len(items) != len(req.ItemIDs) {
		return nil, fmt.Errorf("some question bank items do not exist")
	}
	if count, err := s.bankRepo.CountByIDsInCourse(ctx, req.ItemIDs, courseID); err != nil || int(count) != len(req.ItemIDs) {
		return nil, fmt.Errorf("some items do not belong to this course")
	}
	fallback := &dto.SuggestQuizMetadataResponse{
		Title:        fmt.Sprintf("Bài kiểm tra kiến thức (%d câu)", len(items)),
		Description:  "Bài kiểm tra được tổng hợp từ ngân hàng câu hỏi của khóa học.",
		Instructions: "Đọc kỹ từng câu hỏi và chọn đáp án phù hợp nhất.",
	}
	if s.aiClient == nil {
		return fallback, nil
	}
	questions := make([]string, 0, len(items))
	for _, item := range items {
		questions = append(questions, item.QuestionText)
	}
	suggestion, err := s.aiClient.SuggestBankQuizMetadata(ctx, questions, "vi")
	if err != nil {
		logger.Error("quiz metadata suggestion failed; using fallback", err)
		return fallback, nil
	}
	if strings.TrimSpace(suggestion.Title) != "" {
		fallback.Title = strings.TrimSpace(suggestion.Title)
	}
	if strings.TrimSpace(suggestion.Description) != "" {
		fallback.Description = strings.TrimSpace(suggestion.Description)
	}
	if strings.TrimSpace(suggestion.Instructions) != "" {
		fallback.Instructions = strings.TrimSpace(suggestion.Instructions)
	}
	return fallback, nil
}

// CreateQuizFromBank copies selected bank items into a brand-new quiz.
// Bank items are never consumed (teachers keep reusing them).
func (s *QuestionBankService) CreateQuizFromBank(
	ctx context.Context, courseID, userID int64, userRole string,
	req *dto.CreateQuizFromBankRequest,
) (*dto.CreateQuizFromBankResponse, error) {
	if err := s.verifyCourseEditAccess(ctx, courseID, userID, userRole); err != nil {
		return nil, err
	}
	if req.AvailableFrom != nil && req.AvailableUntil != nil && !req.AvailableUntil.After(*req.AvailableFrom) {
		return nil, fmt.Errorf("available_until must be after available_from")
	}
	if req.TimeLimitMinutes != nil && *req.TimeLimitMinutes < 0 {
		return nil, fmt.Errorf("time_limit_minutes must not be negative")
	}
	if req.MaxAttempts != nil && *req.MaxAttempts < 1 {
		return nil, fmt.Errorf("max_attempts must be at least 1")
	}
	if req.PassingScore != nil && (*req.PassingScore < 0 || *req.PassingScore > 100) {
		return nil, fmt.Errorf("passing_score must be between 0 and 100")
	}
	if len([]rune(strings.TrimSpace(req.Title))) > 255 {
		return nil, fmt.Errorf("title must not exceed 255 characters")
	}

	// Preferred one-click flow: create the QUIZ content inside the chosen
	// section here, so the browser cannot leave an orphan content row when quiz
	// assembly fails. Older clients may still provide an existing ContentID.
	contentID := req.ContentID
	createdContent := false
	if contentID == 0 {
		if req.SectionID <= 0 {
			return nil, fmt.Errorf("section_id is required")
		}
		section, err := s.courseRepo.GetSectionByID(ctx, req.SectionID)
		if err != nil || section.CourseID != courseID {
			return nil, fmt.Errorf("section does not belong to this course")
		}
		contents, err := s.courseRepo.ListContentBySection(ctx, req.SectionID)
		if err != nil {
			return nil, fmt.Errorf("failed to inspect section contents: %w", err)
		}
		nextOrder := 0
		for _, existing := range contents {
			if existing.OrderIndex >= nextOrder {
				nextOrder = existing.OrderIndex + 1
			}
		}
		created, err := s.courseRepo.CreateContent(ctx, &models.SectionContent{
			SectionID:   req.SectionID,
			Type:        models.ContentTypeQuiz,
			Title:       strings.TrimSpace(req.Title),
			Description: toNullString(req.Description),
			OrderIndex:  nextOrder,
			Metadata:    []byte("{}"),
			IsPublished: req.IsPublished,
			IsMandatory: true,
			CreatedBy:   userID,
		})
		if err != nil {
			return nil, fmt.Errorf("failed to create quiz content: %w", err)
		}
		contentID = created.ID
		createdContent = true
	} else {
		content, err := s.courseRepo.GetContentByID(ctx, contentID)
		if err != nil {
			return nil, fmt.Errorf("content not found")
		}
		section, err := s.courseRepo.GetSectionByID(ctx, content.SectionID)
		if err != nil || section.CourseID != courseID {
			return nil, fmt.Errorf("content does not belong to this course")
		}
		if content.Type != models.ContentTypeQuiz {
			return nil, fmt.Errorf("content is not a quiz")
		}
	}
	createdQuizID := int64(0)
	cleanup := func() {
		if createdQuizID > 0 {
			if err := s.quizRepo.DeleteQuiz(ctx, createdQuizID); err != nil {
				logger.Error("from-bank: failed to clean up quiz", err)
			}
		}
		if createdContent {
			if err := s.courseRepo.DeleteContent(ctx, contentID); err != nil {
				logger.Error("from-bank: failed to clean up quiz content", err)
			}
		}
	}

	// Fetch + validate every requested item belongs to that course.
	items, err := s.bankRepo.GetByIDs(ctx, req.ItemIDs)
	if err != nil {
		cleanup()
		return nil, err
	}
	if len(items) != len(req.ItemIDs) {
		cleanup()
		return nil, fmt.Errorf("some question bank items do not exist")
	}
	idsInCourse := make([]int64, len(items))
	totalPoints := 0.0
	for i, item := range items {
		idsInCourse[i] = item.ID
		totalPoints += item.Points
	}
	n, err := s.bankRepo.CountByIDsInCourse(ctx, idsInCourse, courseID)
	if err != nil {
		cleanup()
		return nil, err
	}
	if int(n) != len(req.ItemIDs) {
		cleanup()
		return nil, fmt.Errorf("some items do not belong to this course")
	}

	// Quiz shell.
	totalPointsOut := totalPoints
	if req.TotalPoints != nil && *req.TotalPoints >= 0 {
		totalPointsOut = *req.TotalPoints
	}
	maxAttempts := 3
	if req.MaxAttempts != nil && *req.MaxAttempts > 0 {
		maxAttempts = *req.MaxAttempts
	}
	quiz := &models.Quiz{
		ContentID:              contentID,
		Title:                  strings.TrimSpace(req.Title),
		Description:            toNullString(req.Description),
		Instructions:           toNullString(req.Instructions),
		TimeLimitMinutes:       toNullInt32(req.TimeLimitMinutes),
		AvailableFrom:          toNullTime(req.AvailableFrom),
		AvailableUntil:         toNullTime(req.AvailableUntil),
		MaxAttempts:            toNullInt32(&maxAttempts),
		ShuffleQuestions:       req.ShuffleQuestions,
		ShuffleAnswers:         req.ShuffleAnswers,
		PassingScore:           toNullFloat64(req.PassingScore),
		TotalPoints:            totalPointsOut,
		AutoGrade:              req.AutoGrade,
		ShowResultsImmediately: true,
		ShowCorrectAnswers:     true,
		AllowReview:            true,
		ShowFeedback:           true,
		IsPublished:            req.IsPublished,
		CreatedBy:              userID,
	}

	if err := s.quizRepo.CreateQuiz(ctx, quiz); err != nil {
		cleanup()
		return nil, fmt.Errorf("failed to create quiz: %w", err)
	}
	createdQuizID = quiz.ID

	// Copy items -> quiz questions (+options +correct answers).
	added := 0
	for i, item := range items {
		q := &models.QuizQuestion{
			QuizID:       quiz.ID,
			QuestionType: item.QuestionType,
			QuestionText: item.QuestionText,
			Explanation:  item.Explanation,
			Points:       item.Points,
			OrderIndex:   i + 1,
			Settings:     item.SettingsRaw(),
			IsRequired:   true,
			NodeID:       item.NodeID,
			BloomLevel:   item.BloomLevel,
		}
		if err := s.quizRepo.CreateQuestion(ctx, q); err != nil {
			cleanup()
			return nil, fmt.Errorf("failed to copy bank item %d: %w", item.ID, err)
		}
		added++

		var options []dto.CreateAnswerOptionRequest
		if len(item.AnswerOptionsRaw()) > 0 {
			_ = json.Unmarshal(item.AnswerOptionsRaw(), &options)
		}
		for _, opt := range options {
			o := &models.QuizAnswerOption{
				QuestionID: q.ID,
				OptionText: opt.OptionText,
				OptionHTML: toNullString(opt.OptionHTML),
				IsCorrect:  opt.IsCorrect,
				OrderIndex: opt.OrderIndex,
				BlankID:    toNullInt32(opt.BlankID),
			}
			if err := s.quizRepo.CreateAnswerOption(ctx, o); err != nil {
				cleanup()
				return nil, fmt.Errorf("failed to copy answer option: %w", err)
			}
		}

		var answers []dto.CreateCorrectAnswerRequest
		if len(item.CorrectAnswersRaw()) > 0 {
			_ = json.Unmarshal(item.CorrectAnswersRaw(), &answers)
		}
		for _, ans := range answers {
			a := &models.QuizCorrectAnswer{
				QuestionID:    q.ID,
				AnswerText:    toNullString(ans.AnswerText),
				BlankID:       toNullInt32(ans.BlankID),
				BlankPosition: toNullInt32(ans.BlankPosition),
				CaseSensitive: ans.CaseSensitive,
				ExactMatch:    ans.ExactMatch,
			}
			if err := s.quizRepo.CreateCorrectAnswer(ctx, a); err != nil {
				cleanup()
				return nil, fmt.Errorf("failed to copy correct answer: %w", err)
			}
		}
	}

	return &dto.CreateQuizFromBankResponse{
		QuizID: quiz.ID, ContentID: contentID, QuestionsAdded: added, IsPublished: req.IsPublished,
	}, nil
}

// ToBankItemResponse converts a model into its API shape.
func ToBankItemResponse(m *models.QuestionBankItem) *dto.BankItemResponse {
	resp := &dto.BankItemResponse{
		ID:             m.ID,
		CourseID:       m.CourseID,
		QuestionType:   m.QuestionType,
		QuestionText:   m.QuestionText,
		Explanation:    m.Explanation.String,
		Points:         m.Points,
		BloomLevel:     m.BloomLevel.String,
		Difficulty:     m.Difficulty,
		Tags:           m.Tags,
		Source:         m.Source,
		Status:         m.Status,
		CreatedBy:      m.CreatedBy,
		CreatedAt:      m.CreatedAt,
		UpdatedAt:      m.UpdatedAt,
		AnswerOptions:  json.RawMessage(orEmptyArray(m.AnswerOptionsRaw())),
		CorrectAnswers: json.RawMessage(orEmptyArray(m.CorrectAnswersRaw())),
		Settings:       json.RawMessage(orEmptyObject(m.SettingsRaw())),
	}
	if m.NodeID.Valid {
		v := m.NodeID.Int64
		resp.NodeID = &v
	}
	if m.SourceQuizID.Valid {
		v := m.SourceQuizID.Int64
		resp.SourceQuizID = &v
	}
	return resp
}

func orEmptyArray(b []byte) string {
	if len(b) == 0 {
		return "[]"
	}
	return string(b)
}

func orEmptyObject(b []byte) string {
	if len(b) == 0 {
		return "{}"
	}
	return string(b)
}

// GenerateIntoBankRequest - teacher-facing knobs for AI generation.
// An empty NodeIDs list samples the whole course graph. A non-empty list
// restricts generation to those course-owned knowledge nodes.
type GenerateIntoBankRequest struct {
	Count       int      `json:"count" binding:"omitempty,min=1,max=30"`
	BloomLevels []string `json:"bloom_levels"`
	NodeIDs     []int64  `json:"node_ids" binding:"omitempty,max=100,dive,gt=0"`
	Language    string   `json:"language"`
}

// GenerateIntoBank orchestrates: access check -> gather existing questions
// (anti-duplication context) -> AI auto-generation -> persisted bank items.
func (s *QuestionBankService) GenerateIntoBank(
	ctx context.Context, courseID, userID int64, userRole string,
	req *GenerateIntoBankRequest,
) ([]*dto.BankItemResponse, int, error) {
	if err := s.verifyCourseEditAccess(ctx, courseID, userID, userRole); err != nil {
		return nil, 0, err
	}
	if s.aiClient == nil {
		return nil, 0, fmt.Errorf("AI service unavailable")
	}

	count := req.Count
	if count <= 0 {
		count = 10
	}
	language := req.Language
	if language == "" {
		language = "vi"
	}

	excludes, err := s.bankRepo.RecentTexts(ctx, courseID, 200)
	if err != nil {
		return nil, 0, err
	}

	gen, err := s.aiClient.GenerateToBank(ctx, ai.GenerateToBankRequest{
		CourseID:         courseID,
		Count:            count,
		BloomLevels:      req.BloomLevels,
		NodeIDs:          req.NodeIDs,
		Language:         language,
		ExcludeQuestions: excludes,
	})
	if err != nil {
		return nil, 0, fmt.Errorf("AI generation failed: %w", err)
	}
	if len(gen.Questions) == 0 {
		return []*dto.BankItemResponse{}, gen.RejectedCount, nil
	}

	// Map generated payloads into the standard create contract so storage
	// goes through exactly one validated path.
	items := make([]dto.CreateBankItemRequest, 0, len(gen.Questions))
	for _, q := range gen.Questions {
		options := make([]dto.CreateAnswerOptionRequest, 0, len(q.AnswerOptions))
		for _, o := range q.AnswerOptions {
			isCorrect, _ := o["is_correct"].(bool)
			optionText, _ := o["option_text"].(string)
			orderIdx, _ := o["order_index"].(float64)
			options = append(options, dto.CreateAnswerOptionRequest{
				OptionText: optionText,
				IsCorrect:  isCorrect,
				OrderIndex: int(orderIdx),
			})
		}
		correctAnswers := make([]dto.CreateCorrectAnswerRequest, 0, len(q.CorrectAnswers))
		for _, a := range q.CorrectAnswers {
			correctAnswers = append(correctAnswers, dto.CreateCorrectAnswerRequest{
				AnswerText:    stringValue(a["answer_text"]),
				BlankID:       optionalIntValue(a["blank_id"]),
				BlankPosition: optionalIntValue(a["blank_position"]),
				CaseSensitive: boolValue(a["case_sensitive"]),
				ExactMatch:    boolValue(a["exact_match"]),
			})
		}
		var nodeID *int64
		if q.NodeID != nil && *q.NodeID > 0 {
			nodeID = q.NodeID
		}
		points := q.Points
		if points <= 0 {
			points = 10
		}
		items = append(items, dto.CreateBankItemRequest{
			NodeID:         nodeID,
			QuestionType:   dto.QuestionType(q.QuestionType),
			QuestionText:   q.QuestionText,
			Explanation:    q.Explanation,
			Points:         &points,
			BloomLevel:     q.BloomLevel,
			Difficulty:     q.Difficulty,
			AnswerOptions:  options,
			CorrectAnswers: correctAnswers,
			Settings:       q.Settings,
			Source:         models.BankSourceAIGenerated,
			Status:         models.BankStatusApproved,
		})
	}

	created, err := s.CreateItems(ctx, courseID, userID, userRole, &dto.CreateBankItemsRequest{Items: items})
	if err != nil {
		return nil, gen.RejectedCount, err
	}
	return created, gen.RejectedCount, nil
}

func stringValue(v interface{}) string {
	s, _ := v.(string)
	return s
}

func boolValue(v interface{}) bool {
	b, _ := v.(bool)
	return b
}

func optionalIntValue(v interface{}) *int {
	var n int
	switch value := v.(type) {
	case float64:
		n = int(value)
	case int:
		n = value
	case int64:
		n = int(value)
	default:
		return nil
	}
	return &n
}
