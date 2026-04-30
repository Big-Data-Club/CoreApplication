import { lmsApiClient } from "./lmsApiClient";

export interface Flashcard {
  id: number;
  node_id: number | null;
  lesson_id?: number | null;
  content_id?: number | null;
  course_id: number;
  front_text: string;
  back_text: string;
  language: string;
}

export interface FlashcardRepetition {
  id: number;
  flashcard_id: number;
  easiness_factor: number;
  interval_days: number;
  repetitions: number;
  next_review_date: string;
  last_reviewed_at: string;
}

export interface FlashcardDueItem {
  id: number;
  course_id: number;
  node_id: number | null;
  lesson_id?: number | null;
  content_id?: number | null;
  front_text: string;
  back_text: string;
  status: string;
  next_review_date: string;
}

export interface GenerateFlashcardsRequest {
  count: number;
  lesson_id?: number | null;
  content_id?: number | null;
  text_chunk?: string;
}

export interface BulkSaveFlashcardsRequest {
  node_id?: number | null;
  lesson_id?: number | null;
  content_id?: number | null;
  flashcards: Array<{ front_text: string; back_text: string }>;
}

export interface FlashcardWithRepetition extends FlashcardDueItem {
  easiness_factor?: number;
  interval_days?: number;
  repetitions?: number;
  last_reviewed_at?: string;
  created_at: string;
}

class FlashcardService {
  /**
   * Generate highly personalized flashcards
   */
  async generateFlashcards(
    courseId: number,
    nodeId: number | null,
    req: GenerateFlashcardsRequest
  ): Promise<{ job_id: string; status: string }> {
    const url = nodeId
      ? `/courses/${courseId}/nodes/${nodeId}/flashcards/generate`
      : `/courses/${courseId}/flashcards/generate`;
    const response = await lmsApiClient.post(url, req);
    return response.data?.data ?? response.data;
  }

  /**
   * Bulk save flashcards (e.g. from concept check)
   */
  async bulkSaveFlashcards(
    courseId: number,
    req: BulkSaveFlashcardsRequest
  ): Promise<{ data: FlashcardWithRepetition[] }> {
    const response = await lmsApiClient.post(`/courses/${courseId}/flashcards/bulk-save`, req);
    return response.data;
  }

  /**
   * List flashcards due today
   */
  async listDueFlashcards(courseId: number): Promise<{ data: FlashcardDueItem[] }> {
    const response = await lmsApiClient.get(`/courses/${courseId}/flashcards/due`);
    return response.data;
  }

  /**
   * List all flashcards for a specific target (node or lesson)
   */
  async listFlashcards(courseId: number, nodeId?: number | null, lessonId?: number | null, contentId?: number | null): Promise<{ data: FlashcardWithRepetition[] }> {
    const params = new URLSearchParams();
    if (nodeId) params.append("nodeId", nodeId.toString());
    if (lessonId) params.append("lessonId", lessonId.toString());
    if (contentId) params.append("contentId", contentId.toString());
    
    const response = await lmsApiClient.get(`/courses/${courseId}/flashcards?${params.toString()}`);
    return response.data;
  }

  /**
   * Record a review (0 to 5) for a flashcard
   */
  async reviewFlashcard(flashcardId: number, quality: number): Promise<{ data: FlashcardRepetition }> {
    const response = await lmsApiClient.post(`/flashcards/${flashcardId}/review`, { quality });
    return response.data;
  }
}

export const flashcardService = new FlashcardService();
export default flashcardService;
