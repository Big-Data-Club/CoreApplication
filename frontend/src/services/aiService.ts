/**
 * aiService.ts
 * Frontend client for all AI features (Phase 1 & 2).
 * Calls Go lms-service endpoints which proxy to ai-service internally.
 */
import { lmsApiClient } from "./lmsApiClient";

// ─── Phase 1: Diagnosis ───────────────────────────────────────────────────────

export interface DeepLink {
  content_id?: number;
  source_type: "document" | "video";
  page_number?: number;
  start_time_sec?: number;
  end_time_sec?: number;
  url_fragment?: string;
  file_url?: string;
  title?: string;
  content_type?: string;
  snippet?: string;
}

export interface DiagnosisResult {
  explanation: string;
  gap_type: "misconception" | "missing_prerequisite" | "careless_error" | "unknown";
  knowledge_gap: string;
  study_suggestion: string;
  confidence: number;
  source_chunk_id?: number;
  suggested_documents?: DeepLink[];
  language: string;
}

export interface HeatmapNode {
  node_id: number;
  node_name: string;
  name_vi?: string;
  student_count: number;
  avg_mastery: number;
  total_wrong: number;
  total_attempts: number;
  wrong_rate: number;
}

// ─── Phase 2: Quiz Gen & Spaced Repetition ─────────────────────────────────

export interface GeneratedQuestion {
  id: number;
  node_id: number;
  node_name?: string;
  course_id: number;
  bloom_level: string;
  question_text: string;
  question_type: string;
  answer_options: { text: string; is_correct: boolean; explanation: string }[];
  explanation: string;
  source_quote: string;
  source_chunk_id?: number;
  language: string;
  status: "DRAFT" | "APPROVED" | "REJECTED" | "PUBLISHED";
  review_note?: string;
}

export interface DueReview {
  question_id: number;
  node_id?: number;
  next_review_date: string;
  interval_days: number;
  repetitions: number;
  question_text: string;
  question_type: string;
  node_name?: string;
}

export interface ReviewStats {
  due_today: number;
  upcoming: number;
  total_tracked: number;
  avg_easiness?: number;
  avg_repetitions?: number;
}

export interface KnowledgeNode {
  id: number;
  course_id: number;
  parent_id?: number;
  name: string;
  name_vi?: string;
  name_en?: string;
  description?: string;
  level: number;
  order_index: number;
  chunk_count: number;
  auto_generated?: boolean;
  source_content_id?: number;
}

// ─── Knowledge Graph ──────────────────────────────────────────────────────────

export type RelationType = "prerequisite" | "related" | "extends" | "parent_child" | "equivalent" | "contrasts_with";

export interface KnowledgeGraphNode {
  id: number;
  name: string;
  name_vi?: string;
  name_en?: string;
  description?: string;
  source_content_id?: number;
  source_content_title?: string;
  auto_generated: boolean;
  chunk_count: number;
  level: number;
  /** course_id is present on global graph nodes */
  course_id?: number;
}

export interface KnowledgeGraphEdge {
  source: number;
  target: number;
  relation_type: RelationType | string;
  strength: number;
  auto_generated: boolean;
  cross_course?: boolean;
  reason?: string;
}

export interface KnowledgeGraphResponse {
  course_id: number;
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

export interface ChunkItem {
  id: number;
  chunk_text: string;
  chunk_index: number;
  source_type: string;
  page_number?: number;
  start_time_sec?: number;
  end_time_sec?: number;
  language: string;
}

export interface AIJobResponse {
  job_id: string;
  status: string;
}

export interface AIJobStatus<T = any> {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  result?: T;
  error?: string;
}

// ─── Compact Graph (Consolidation) ───────────────────────────────────────

export interface ConsolidationGroup {
  survivor_id: number;
  absorbed_ids: number[];
  new_name: string;
  new_name_vi: string;
  new_description: string;
  new_keywords: string[];
  similarity: number;
  reason: string;
  /** "hard" | "soft" | "micro" */
  kind: string;
  /** Map of "<id>" → display name, including the survivor */
  old_names: Record<string, string>;
}

export interface ConsolidationPreview {
  course_id: number;
  total_nodes_before: number;
  total_nodes_after: number;
  reduction_percent: number;
  groups: ConsolidationGroup[];
}

class AIService {
  // ─── Polling Jobs ────────────────────────────────────────────────────────
  
  async getJobStatus<T = any>(jobId: string): Promise<AIJobStatus<T>> {
    const res = await lmsApiClient.get(`/ai/jobs/${jobId}/status`);
    return res.data?.data ?? res.data;
  }

  // ─── Diagnosis ─────────────────────────────────────────────────────────────

  async diagnoseWrongAnswer(
    attemptId: number,
    questionId: number,
    wrongAnswer: string,
    courseId: number
  ): Promise<AIJobResponse> {
    const res = await lmsApiClient.post(
      `/ai/attempts/${attemptId}/questions/${questionId}/diagnose`,
      {
        wrong_answer: wrongAnswer,
        course_id: courseId,
      }
    );
    return res.data?.data ?? res.data;
  }

  async getClassHeatmap(courseId: number): Promise<HeatmapNode[]> {
    const res = await lmsApiClient.get(`/courses/${courseId}/ai/heatmap`);
    return res.data?.data ?? res.data ?? [];
  }

  async getStudentHeatmap(courseId: number): Promise<HeatmapNode[]> {
    const res = await lmsApiClient.get(`/courses/${courseId}/ai/my-heatmap`);
    return res.data?.data ?? res.data ?? [];
  }

  // ─── Knowledge Nodes ──────────────────────────────────────────────────────

  async listKnowledgeNodes(courseId: number): Promise<KnowledgeNode[]> {
    const res = await lmsApiClient.get(`/courses/${courseId}/ai/nodes`);
    return res.data?.data ?? res.data ?? [];
  }

  async createKnowledgeNode(
    courseId: number,
    data: { name: string; name_vi?: string; description?: string; parent_id?: number }
  ): Promise<KnowledgeNode> {
    const res = await lmsApiClient.post(`/courses/${courseId}/ai/nodes`, data);
    return res.data?.data ?? res.data;
  }

  // ─── Quiz Generation ──────────────────────────────────────────────────────

  async generateQuiz(
    courseId: number,
    nodeId: number,
    options?: {
      bloom_levels?: string[];
      language?: string;
      questions_per_level?: number;
    }
  ): Promise<AIJobResponse> {
    const res = await lmsApiClient.post(`/courses/${courseId}/ai/generate-quiz`, {
      node_id: nodeId,
      ...options,
    });
    return res.data?.data ?? res.data;
  }

  async listDraftQuestions(courseId: number): Promise<GeneratedQuestion[]> {
    const res = await lmsApiClient.get(`/courses/${courseId}/ai/drafts`, {
      params: { _t: Date.now() }
    });
    return res.data?.data ?? res.data ?? [];
  }

  async approveQuestion(
    genId: number,
    quizId: number,
    reviewNote = ""
  ): Promise<void> {
    await lmsApiClient.post(`/ai/quiz-drafts/${genId}/approve`, {
      quiz_id: quizId,
      review_note: reviewNote,
    });
  }

  async rejectQuestion(genId: number, reviewNote: string): Promise<void> {
    await lmsApiClient.post(`/ai/quiz-drafts/${genId}/reject`, { review_note: reviewNote });
  }

  // ─── Spaced Repetition ────────────────────────────────────────────────────

  async getDueReviews(courseId: number): Promise<DueReview[]> {
    const res = await lmsApiClient.get(`/courses/${courseId}/ai/reviews/due`);
    return res.data?.data ?? res.data ?? [];
  }

  async recordReview(
    courseId: number,
    questionId: number,
    quality: 0 | 1 | 2 | 3 | 4 | 5,
    nodeId?: number
  ): Promise<void> {
    await lmsApiClient.post(`/courses/${courseId}/ai/reviews/record`, {
      question_id: questionId,
      quality,
      node_id: nodeId,
    });
  }

  async getReviewStats(courseId: number): Promise<ReviewStats> {
    const res = await lmsApiClient.get(`/courses/${courseId}/ai/reviews/stats`);
    return res.data?.data ?? res.data ?? { due_today: 0, upcoming: 0, total_tracked: 0 };
  }

  async getNodeChunks(courseId: number, nodeId: number): Promise<ChunkItem[]> {
      const res = await lmsApiClient.get(`/courses/${courseId}/ai/nodes/${nodeId}/chunks`)
      return res.data?.data ?? []
  }

  // ─── Knowledge Graph ───────────────────────────────────────────────────────

  async getKnowledgeGraph(courseId: number): Promise<KnowledgeGraphResponse> {
    const res = await lmsApiClient.get(`/courses/${courseId}/ai/knowledge-graph`);
    return res.data?.data ?? { course_id: courseId, nodes: [], edges: [] };
  }

  /**
   * Global knowledge graph — all courses, all nodes, all edges.
   * Used by Admin Dashboard and the global knowledge map page.
   * Requires the ai-service /ai/knowledge-graph/global endpoint
   * to be proxied by Go lms-service at /ai/knowledge-graph/global.
   */
  async getGlobalKnowledgeGraph(params?: {
    min_strength?: number;
    limit?: number;
  }): Promise<KnowledgeGraphResponse> {
    const res = await lmsApiClient.get(`/ai/knowledge-graph/global`, { params });
    return res.data?.data ?? { course_id: 0, nodes: [], edges: [] };
  }

  /**
   * Triggers a system-wide background task to discover and link
   * knowledge nodes across all courses.
   */
  async linkGlobalKnowledgeGraph(): Promise<{ status: string; message: string }> {
    const res = await lmsApiClient.post(`/ai/knowledge-graph/link-global`);
    return res.data?.data ?? res.data;
  }

  /**
   * Deletes a knowledge node across all databases (PG, Qdrant, Neo4j).
   */
  async deleteKnowledgeNode(courseId: number, nodeId: number): Promise<void> {
    await lmsApiClient.delete(`/courses/${courseId}/ai/nodes/${nodeId}`);
  }

  // ─── Compact Graph (intelligent node consolidation) ──────────────────────

  /**
   * Dry-run preview of the merge plan. Mutates nothing on the server.
   */
  async previewGraphConsolidation(courseId: number): Promise<ConsolidationPreview> {
    const res = await lmsApiClient.get(
      `/courses/${courseId}/ai/consolidate-graph/preview`
    );
    return (
      res.data?.data ?? res.data ?? {
        course_id: courseId,
        total_nodes_before: 0,
        total_nodes_after: 0,
        reduction_percent: 0,
        groups: [],
      }
    );
  }

  /**
   * Enqueue a "Compact Graph" Kafka job. Returns a job ID for polling
   * via getJobStatus().
   */
  async triggerGraphConsolidation(
    courseId: number
  ): Promise<{ job_id: string; status: string; message?: string }> {
    const res = await lmsApiClient.post(`/courses/${courseId}/ai/consolidate-graph`);
    return res.data?.data ?? res.data;
  }

  /**
   * Quick Action Panel — generate 1–2 ultra-short MCQ "Concept Check"
   * questions tied to a micro-lesson body or knowledge node.
   */
  async generateConceptCheck(req: ConceptCheckRequest): Promise<ConceptCheckResponse> {
    const res = await lmsApiClient.post(`/ai/concept-check`, {
      text_chunk: req.text_chunk ?? "",
      node_id: req.node_id ?? null,
      course_id: req.course_id ?? null,
      count: req.count ?? 2,
      language: req.language ?? "vi",
    });
    return res.data?.data ?? res.data;
  }
}

// ─── Quick Action Panel — Concept Check ───────────────────────────────

export interface ConceptCheckRequest {
  text_chunk?: string;
  node_id?: number | null;
  course_id?: number | null;
  count?: number;
  language?: "vi" | "en";
}

export interface ConceptCheckOption {
  text: string;
  is_correct: boolean;
  explanation: string;
}

export interface ConceptCheckQuestion {
  question_text: string;
  question_type: string;
  answer_options: ConceptCheckOption[];
}

export interface ConceptCheckResponse {
  node_id?: number | null;
  questions: ConceptCheckQuestion[];
}

export const aiService = new AIService();
export default aiService;