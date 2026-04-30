"use client";

/**
 * QuickActionPanel.tsx
 *
 * Mounted at the bottom of the MicroLessonViewer. Three primary
 * actions sit in a single horizontal bar:
 *
 *   1. Flashcards   — flip-card revision (3–5 cards)
 *   2. Quick Check  — 1–2 ultra-short MCQ generated from this lesson
 *   3. Ask AI       — opens a contextual chat drawer; the lesson body
 *                     is invisibly stitched into the agent's system
 *                     prompt via `system_context`.
 *
 * Selecting a tab expands its panel inline; "Ask AI" instead opens
 * a side drawer because the chat needs the full screen height.
 *
 * A `lesson_view` analytics event fires on first mount; once the
 * student spends 30 seconds on the lesson we also send
 * `lesson_complete`, half-credit completion is automatic via the
 * `lesson_view` event already.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import analyticsService from "@/services/analyticsService";
import FlashcardDeck from "./FlashcardDeck";
import QuickCheck from "./QuickCheck";
import AskAIDrawer from "./AskAIDrawer";
import type { MicroLessonContext, QuickActionTab } from "./types";

interface QuickActionPanelProps {
  ctx: MicroLessonContext;
  /**
   * Optional override — set true after the parent decides the student
   * has finished reading (scrolled to bottom, clicked "Mark complete",
   * etc). Defaults to firing automatically after 30s.
   */
  completionExternal?: boolean;
}

const COMPLETION_THRESHOLD_MS = 30_000;

export function QuickActionPanel({
  ctx,
  completionExternal,
}: QuickActionPanelProps) {
  const [tab, setTab] = useState<QuickActionTab>(null);
  const [askOpen, setAskOpen] = useState(false);

  const lang = ctx.language ?? "vi";

  const labels = useMemo(
    () => ({
      header:
        lang === "vi"
          ? "Hành động nhanh"
          : "Quick Actions",
      flashcards: lang === "vi" ? "Thẻ ghi nhớ" : "Flashcards",
      quickCheck: lang === "vi" ? "Kiểm tra nhanh" : "Quick Check",
      askAI: lang === "vi" ? "Hỏi AI" : "Ask AI",
      flashcardsDesc:
        lang === "vi"
          ? "Ôn lại các thuật ngữ chính."
          : "Review the key terms.",
      quickCheckDesc:
        lang === "vi"
          ? "Trả lời 1–2 câu trắc nghiệm ngắn."
          : "Answer 1–2 short multiple-choice questions.",
      askAIDesc:
        lang === "vi"
          ? "Trao đổi với AI về bài học này."
          : "Chat with AI about this lesson.",
    }),
    [lang],
  );

  /** Fire `lesson_view` once per mount + a delayed `lesson_complete`. */
  useEffect(() => {
    analyticsService.trackMicroInteraction({
      course_id: ctx.courseId,
      lesson_id: ctx.lessonId,
      node_id: ctx.nodeId ?? undefined,
      action_type: "lesson_view",
    });

    const t = setTimeout(() => {
      analyticsService.trackMicroInteraction({
        course_id: ctx.courseId,
        lesson_id: ctx.lessonId,
        node_id: ctx.nodeId ?? undefined,
        action_type: "lesson_complete",
        payload: { reason: "auto_threshold_30s" },
      });
    }, COMPLETION_THRESHOLD_MS);

    return () => clearTimeout(t);
    // ctx fields are stable for the life of one MicroLessonViewer mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx.lessonId]);

  /** External completion override (e.g. parent clicked "Mark complete"). */
  useEffect(() => {
    if (!completionExternal) return;
    analyticsService.trackMicroInteraction({
      course_id: ctx.courseId,
      lesson_id: ctx.lessonId,
      node_id: ctx.nodeId ?? undefined,
      action_type: "lesson_complete",
      payload: { reason: "external" },
    });
  }, [completionExternal, ctx.courseId, ctx.lessonId, ctx.nodeId]);

  const openTab = useCallback(
    (next: Exclude<QuickActionTab, null>) => {
      if (next === "ask_ai") {
        setAskOpen(true);
        return;
      }
      setTab((current) => (current === next ? null : next));
    },
    [],
  );

  return (
    <section
      aria-label={labels.header}
      className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-2xl mt-6 overflow-hidden shadow-sm"
    >
      <header className="px-6 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
          {labels.header}
        </h3>
        {tab && (
          <button
            type="button"
            onClick={() => setTab(null)}
            className="text-xs font-medium text-slate-700 dark:text-slate-300 underline underline-offset-2"
          >
            {lang === "vi" ? "Đóng" : "Close"}
          </button>
        )}
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-slate-200 dark:divide-slate-800">
        <ActionButton
          active={tab === "flashcards"}
          label={labels.flashcards}
          desc={labels.flashcardsDesc}
          onClick={() => openTab("flashcards")}
        />
        <ActionButton
          active={tab === "quick_check"}
          label={labels.quickCheck}
          desc={labels.quickCheckDesc}
          onClick={() => openTab("quick_check")}
        />
        <ActionButton
          active={askOpen}
          label={labels.askAI}
          desc={labels.askAIDesc}
          onClick={() => openTab("ask_ai")}
        />
      </div>

      {tab === "flashcards" && (
        <div className="border-t border-slate-200 dark:border-slate-800">
          <FlashcardDeck ctx={ctx} />
        </div>
      )}
      {tab === "quick_check" && (
        <div className="border-t border-slate-200 dark:border-slate-800">
          <QuickCheck ctx={ctx} />
        </div>
      )}

      <AskAIDrawer
        ctx={ctx}
        open={askOpen}
        onClose={() => setAskOpen(false)}
      />
    </section>
  );
}

interface ActionButtonProps {
  active: boolean;
  label: string;
  desc: string;
  onClick: () => void;
}

function ActionButton({ active, label, desc, onClick }: ActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`text-left px-6 py-4 transition-colors focus:outline-none focus:bg-slate-50 dark:focus:bg-slate-800 ${
        active ? "bg-slate-100 dark:bg-slate-800" : "bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800/50"
      }`}
    >
      <span className="block text-sm font-semibold text-slate-900 dark:text-slate-50">
        {label}
      </span>
      <span className="block text-xs text-slate-500 dark:text-slate-400 mt-0.5">{desc}</span>
    </button>
  );
}

export default QuickActionPanel;
