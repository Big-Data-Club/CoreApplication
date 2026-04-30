/**
 * Shared TypeScript types for the Quick Action Panel mounted at the
 * bottom of the MicroLessonViewer.
 *
 * Three primary actions live here:
 *   1. Flashcards   — flip-card revision of 3–5 key terms
 *   2. Quick Check  — 1–2 ultra-short MCQ generated from this lesson
 *   3. Ask AI       — contextual chat drawer pre-loaded with the lesson body
 *
 * Every interaction calls `analyticsService.trackMicroInteraction(...)`.
 */

export interface MicroLessonContext {
  /** Lesson row id from `micro_lessons.id` (Postgres). Null for regular TEXT content. */
  lessonId: number | null;
  /** Lesson title — shown in headers and Ask-AI greeting. */
  lessonTitle: string;
  /** Verbatim Markdown body — fed to the chatbot as system_context. */
  lessonText: string;
  /** Course this lesson belongs to. */
  courseId: number;
  /**
   * Knowledge node the lesson is anchored to (nullable — some draft
   * lessons have no node attached yet).
   */
  nodeId: number | null;
  /** Primary content ID (from `contents` table). Used as fallback anchor if lessonId is null. */
  contentId?: number | null;
  /** Display language: "vi" | "en". Defaults to "vi". */
  language?: "vi" | "en";
}

export type QuickActionTab = "flashcards" | "quick_check" | "ask_ai" | null;
