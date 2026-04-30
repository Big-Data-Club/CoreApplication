"use client";

/**
 * QuickCheck.tsx
 *
 * "Quick Check" tab of the Quick Action Panel: 1–2 ultra-short MCQ
 * questions generated on-the-fly by the AI service, grounded in the
 * current micro-lesson body (`text_chunk`) so the quiz is guaranteed
 * to be answerable from what the student just read.
 *
 * Analytics events:
 *   * quick_check_attempt   — every submitted answer (with score 0/1)
 *   * quick_check_correct   — convenience event for correct submissions
 *   * quick_check_incorrect — convenience event for wrong submissions
 *
 * The composite mastery worker on the LMS side blends `quick_check_*`
 * events into the "mini quiz" component (20% weight) of the heatmap.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import aiService, {
  type ConceptCheckQuestion,
} from "@/services/aiService";
import flashcardService from "@/services/flashcardService";
import analyticsService from "@/services/analyticsService";
import type { MicroLessonContext } from "./types";

interface QuickCheckProps {
  ctx: MicroLessonContext;
}

interface QuestionState {
  selectedIdx: number | null;
  submitted: boolean;
}

export function QuickCheck({ ctx }: QuickCheckProps) {
  const [questions, setQuestions] = useState<ConceptCheckQuestion[]>([]);
  const [state, setState] = useState<QuestionState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const lang = ctx.language ?? "vi";

  const labels = useMemo(
    () => ({
      loading:
        lang === "vi"
          ? "Đang tạo câu hỏi nhanh…"
          : "Generating quick check…",
      empty:
        lang === "vi"
          ? "Không tạo được câu hỏi cho bài học này."
          : "No quick check available for this lesson.",
      submit: lang === "vi" ? "Kiểm tra" : "Check",
      correct: lang === "vi" ? "Chính xác." : "Correct.",
      incorrect: lang === "vi" ? "Chưa đúng." : "Not quite.",
      regenerate: lang === "vi" ? "Tạo bộ câu mới" : "Regenerate",
      save: lang === "vi" ? "Lưu lại ôn tập" : "Save for review",
      saving: lang === "vi" ? "Đang lưu…" : "Saving…",
      saved: lang === "vi" ? "Đã lưu vào Flashcard" : "Saved to Flashcards",
      saveError: lang === "vi" ? "Lỗi khi lưu" : "Failed to save",
    }),
    [lang],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await aiService.generateConceptCheck({
        // Sending the lesson body directly is the "cheap path" — the
        // AI service skips RAG retrieval and grounds the question in
        // exactly what the student is reading.
        text_chunk: ctx.lessonText,
        node_id: ctx.nodeId ?? undefined,
        course_id: ctx.courseId,
        count: 2,
        language: lang,
      });
      const qs = res.questions ?? [];
      setQuestions(qs);
      setState(qs.map(() => ({ selectedIdx: null, submitted: false })));
    } catch (e) {
      setError(
        lang === "vi"
          ? "Không tạo được câu hỏi. Thử lại sau."
          : "Failed to generate questions. Please retry.",
      );
    } finally {
      setLoading(false);
    }
  }, [ctx.courseId, ctx.lessonText, ctx.nodeId, lang]);

  useEffect(() => {
    load();
  }, [load]);

  const onSubmit = useCallback(
    (qIdx: number) => {
      const q = questions[qIdx];
      const s = state[qIdx];
      if (!q || !s || s.selectedIdx == null || s.submitted) return;

      const isCorrect = q.answer_options[s.selectedIdx]?.is_correct === true;
      const score = isCorrect ? 1 : 0;

      // Mark this question as submitted.
      setState((prev) =>
        prev.map((row, i) => (i === qIdx ? { ...row, submitted: true } : row)),
      );

      // Two events: aggregate score + correctness flag. The heatmap
      // worker blends them into the mini-quiz component.
      analyticsService.trackMicroInteraction({
        course_id: ctx.courseId,
        lesson_id: ctx.lessonId,
        node_id: ctx.nodeId ?? undefined,
        action_type: "quick_check_attempt",
        score,
        status: isCorrect ? "correct" : "incorrect",
      });
      analyticsService.trackMicroInteraction({
        course_id: ctx.courseId,
        lesson_id: ctx.lessonId,
        node_id: ctx.nodeId ?? undefined,
        action_type: isCorrect ? "quick_check_correct" : "quick_check_incorrect",
      });
  }, [ctx.courseId, ctx.lessonId, ctx.nodeId, questions, state]);

  const handleSave = useCallback(async () => {
    if (saving || saved || questions.length === 0) return;
    setSaving(true);
    try {
      const flashcards = questions.map((q) => {
        // Front: Question + Options (A, B, C, D)
        const optionsText = q.answer_options
          .map((opt, i) => `${String.fromCharCode(65 + i)}. ${opt.text}`)
          .join("\n");
        const front_text = `${q.question_text}\n\n${optionsText}`;

        // Back: Correct Answer + Explanation
        const correctOpt = q.answer_options.find((o) => o.is_correct);
        const correctIndex = q.answer_options.findIndex((o) => o.is_correct);
        const correctLetter = String.fromCharCode(65 + correctIndex);
        
        let back_text = `Đáp án đúng: ${correctLetter}. ${correctOpt?.text || ""}`;
        if (correctOpt?.explanation) {
          back_text += `\n\nGiải thích: ${correctOpt.explanation}`;
        }

        return { front_text, back_text };
      });

      await flashcardService.bulkSaveFlashcards(ctx.courseId, {
        node_id: ctx.nodeId,
        lesson_id: ctx.lessonId,
        content_id: ctx.contentId,
        flashcards,
      });
      setSaved(true);
    } catch (e) {
      alert(labels.saveError);
    } finally {
      setSaving(false);
    }
  }, [ctx.courseId, ctx.lessonId, ctx.nodeId, questions, saved, saving, labels]);

  if (loading) {
    return (
      <div className="px-6 py-10 text-sm text-slate-500 dark:text-slate-400 text-center">
        {labels.loading}
      </div>
    );
  }
  if (error) {
    return (
      <div className="px-6 py-10 text-sm text-red-600 dark:text-red-400 text-center">
        {error}
        <div className="mt-3">
          <button
            type="button"
            onClick={load}
            className="text-xs font-medium text-slate-900 dark:text-slate-100 underline underline-offset-2"
          >
            {labels.regenerate}
          </button>
        </div>
      </div>
    );
  }
  if (questions.length === 0) {
    return (
      <div className="px-6 py-10 text-sm text-slate-500 dark:text-slate-400 text-center">
        {labels.empty}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 px-6 py-5">
      {questions.map((q, qIdx) => {
        const s = state[qIdx];
        return (
          <div
            key={qIdx}
            className="border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-900"
          >
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 text-sm font-semibold text-slate-900 dark:text-slate-50">
              {q.question_text}
            </div>
            <div className="flex flex-col">
              {q.answer_options.map((opt, oIdx) => {
                const selected = s?.selectedIdx === oIdx;
                const correct = s?.submitted && opt.is_correct;
                const wrong = s?.submitted && selected && !opt.is_correct;
                const base =
                  "text-left text-sm px-4 py-2.5 border-t border-slate-100 dark:border-slate-800 transition-colors";
                const stateCls = correct
                  ? "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-900 dark:text-emerald-300"
                  : wrong
                    ? "bg-red-50 dark:bg-red-950/30 text-red-900 dark:text-red-300"
                    : selected
                      ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/50";
                return (
                  <button
                    type="button"
                    key={oIdx}
                    disabled={s?.submitted}
                    onClick={() =>
                      setState((prev) =>
                        prev.map((row, i) =>
                          i === qIdx ? { ...row, selectedIdx: oIdx } : row,
                        ),
                      )
                    }
                    className={`${base} ${stateCls} disabled:cursor-default`}
                  >
                    <span className="inline-block w-5 text-slate-400 dark:text-slate-500 mr-1">
                      {String.fromCharCode(65 + oIdx)}.
                    </span>
                    {opt.text}
                    {s?.submitted && opt.explanation && (correct || wrong) && (
                      <span className="block mt-1 text-xs text-slate-600 dark:text-slate-400">
                        {opt.explanation}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {s?.submitted
                  ? q.answer_options[s.selectedIdx ?? -1]?.is_correct
                    ? labels.correct
                    : labels.incorrect
                  : ""}
              </span>
              <button
                type="button"
                disabled={!s || s.selectedIdx == null || s.submitted}
                onClick={() => onSubmit(qIdx)}
                className="px-3 py-1.5 text-xs font-medium border border-slate-900 dark:border-slate-200 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-sm disabled:bg-slate-400 disabled:border-slate-400 dark:disabled:bg-slate-700 dark:disabled:border-slate-700 dark:disabled:text-slate-500"
              >
                {labels.submit}
              </button>
            </div>
          </div>
        );
      })}

      <div className="flex items-center justify-between mt-2">
        <button
          type="button"
          onClick={load}
          className="text-xs font-medium text-slate-700 dark:text-slate-300 underline underline-offset-2"
        >
          {labels.regenerate}
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || saved}
          className={`px-4 py-2 text-xs font-medium rounded-md transition-colors ${
            saved
              ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
              : "border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50"
          }`}
        >
          {saving ? labels.saving : saved ? labels.saved : labels.save}
        </button>
      </div>
    </div>
  );
}

export default QuickCheck;
