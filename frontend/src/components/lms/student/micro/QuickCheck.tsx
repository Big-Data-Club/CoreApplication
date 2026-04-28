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
    },
    [ctx.courseId, ctx.lessonId, ctx.nodeId, questions, state],
  );

  if (loading) {
    return (
      <div className="px-6 py-10 text-sm text-slate-500 text-center">
        {labels.loading}
      </div>
    );
  }
  if (error) {
    return (
      <div className="px-6 py-10 text-sm text-red-600 text-center">
        {error}
        <div className="mt-3">
          <button
            type="button"
            onClick={load}
            className="text-xs font-medium text-slate-900 underline underline-offset-2"
          >
            {labels.regenerate}
          </button>
        </div>
      </div>
    );
  }
  if (questions.length === 0) {
    return (
      <div className="px-6 py-10 text-sm text-slate-500 text-center">
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
            className="border border-slate-200 rounded-md bg-white"
          >
            <div className="px-4 py-3 border-b border-slate-200 text-sm font-semibold text-slate-900">
              {q.question_text}
            </div>
            <div className="flex flex-col">
              {q.answer_options.map((opt, oIdx) => {
                const selected = s?.selectedIdx === oIdx;
                const correct = s?.submitted && opt.is_correct;
                const wrong = s?.submitted && selected && !opt.is_correct;
                const base =
                  "text-left text-sm px-4 py-2.5 border-t border-slate-100 transition-colors";
                const stateCls = correct
                  ? "bg-emerald-50 text-emerald-900"
                  : wrong
                    ? "bg-red-50 text-red-900"
                    : selected
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-700 hover:bg-slate-50";
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
                    <span className="inline-block w-5 text-slate-400 mr-1">
                      {String.fromCharCode(65 + oIdx)}.
                    </span>
                    {opt.text}
                    {s?.submitted && opt.explanation && (correct || wrong) && (
                      <span className="block mt-1 text-xs text-slate-600">
                        {opt.explanation}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 bg-slate-50">
              <span className="text-xs text-slate-500">
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
                className="px-3 py-1.5 text-xs font-medium border border-slate-900 bg-slate-900 text-white rounded-sm disabled:bg-slate-400 disabled:border-slate-400"
              >
                {labels.submit}
              </button>
            </div>
          </div>
        );
      })}

      <div>
        <button
          type="button"
          onClick={load}
          className="text-xs font-medium text-slate-700 underline underline-offset-2"
        >
          {labels.regenerate}
        </button>
      </div>
    </div>
  );
}

export default QuickCheck;
