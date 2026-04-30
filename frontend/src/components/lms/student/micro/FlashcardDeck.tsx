"use client";

/**
 * FlashcardDeck.tsx
 *
 * Minimalist flip-card UI for the Quick Action Panel "Flashcards" tab.
 * Pulls 3–5 cards anchored to the active micro-lesson's node and lets
 * the student step through them. Every flip and "Got it / Need review"
 * tap fires an analytics event.
 *
 * Visual language: solid neutral surfaces, hairline borders, no
 * gradients or playful icons.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import flashcardService, {
  FlashcardWithRepetition,
} from "@/services/flashcardService";
import analyticsService from "@/services/analyticsService";
import type { MicroLessonContext } from "./types";

interface FlashcardDeckProps {
  ctx: MicroLessonContext;
}

export function FlashcardDeck({ ctx }: FlashcardDeckProps) {
  const [cards, setCards] = useState<FlashcardWithRepetition[]>([]);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const lang = ctx.language ?? "vi";

  // Load 3–5 cards. Skip the network call entirely when no node_id and no lesson_id is attached.
  useEffect(() => {
    if (ctx.nodeId == null && ctx.lessonId == null && ctx.contentId == null) {
      setLoading(false);
      setCards([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await flashcardService.listFlashcards(
          ctx.courseId,
          ctx.nodeId,
          ctx.lessonId,
          ctx.contentId
        );
        if (cancelled) return;
        setCards(res.data ?? []);
        setError("");
      } catch (e) {
        if (cancelled) return;
        setError(
          lang === "vi"
            ? "Không tải được flashcard."
            : "Failed to load flashcards.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ctx.courseId, ctx.nodeId, ctx.lessonId, ctx.contentId, lang, reloadKey]);

  const handleGenerate = useCallback(async () => {
    if ((ctx.nodeId == null && ctx.lessonId == null && ctx.contentId == null) || generating) return;
    setGenerating(true);
    setError("");
    try {
      await flashcardService.generateFlashcards(ctx.courseId, ctx.nodeId ?? null, {
        count: 5,
        lesson_id: ctx.lessonId,
        content_id: ctx.contentId,
        text_chunk: ctx.lessonText,
      });
      // Reload the card list after generation
      setReloadKey((k) => k + 1);
    } catch (e) {
      setError(
        lang === "vi"
          ? "Không thể tạo flashcard. Vui lòng thử lại."
          : "Failed to generate flashcards. Please try again.",
      );
    } finally {
      setGenerating(false);
    }
  }, [ctx.courseId, ctx.nodeId, ctx.lessonId, ctx.contentId, ctx.lessonText, generating, lang]);

  const current = cards[index];

  const track = useCallback(
    (action: "flashcard_flip" | "flashcard_rate", payload?: Record<string, unknown>) => {
      analyticsService.trackMicroInteraction({
        course_id: ctx.courseId,
        lesson_id: ctx.lessonId,
        node_id: ctx.nodeId ?? undefined,
        action_type: action,
        payload,
      });
    },
    [ctx.courseId, ctx.lessonId, ctx.nodeId],
  );

  const handleFlip = useCallback(() => {
    setFlipped((f) => {
      const next = !f;
      // Only count a flip when going from front → back; otherwise it's
      // a "go back to question" interaction, not real engagement.
      if (next && current) {
        track("flashcard_flip", { flashcard_id: current.id });
      }
      return next;
    });
  }, [current, track]);

  const handleRate = useCallback(
    (quality: number) => {
      if (!current) return;
      flashcardService.reviewFlashcard(current.id, quality).catch(() => undefined);
      track("flashcard_rate", { flashcard_id: current.id, quality });
      // Auto-advance to next card.
      if (index < cards.length - 1) {
        setIndex((i) => i + 1);
        setFlipped(false);
      }
    },
    [cards.length, current, index, track],
  );

  const handlePrev = useCallback(() => {
    if (index > 0) {
      setIndex((i) => i - 1);
      setFlipped(false);
    }
  }, [index]);

  const handleNext = useCallback(() => {
    if (index < cards.length - 1) {
      setIndex((i) => i + 1);
      setFlipped(false);
    }
  }, [index, cards.length]);

  const labels = useMemo(
    () => ({
      front: lang === "vi" ? "Mặt trước" : "Front",
      back: lang === "vi" ? "Mặt sau" : "Back",
      flip: lang === "vi" ? "Lật thẻ" : "Flip card",
      again: lang === "vi" ? "Cần ôn lại" : "Need review",
      good: lang === "vi" ? "Đã hiểu" : "Got it",
      empty:
        lang === "vi"
          ? "Chưa có flashcard cho bài học này."
          : "No flashcards available for this lesson yet.",
      loading: lang === "vi" ? "Đang tải…" : "Loading…",
      counter: (i: number, n: number) =>
        lang === "vi" ? `Thẻ ${i}/${n}` : `Card ${i}/${n}`,
    }),
    [lang],
  );

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
      </div>
    );
  }
  if (cards.length === 0 || !current) {
    return (
      <div className="px-6 py-10 text-sm text-slate-500 dark:text-slate-400 text-center flex flex-col items-center gap-3">
        <span>{labels.empty}</span>
        {(ctx.nodeId != null || ctx.lessonId != null || ctx.contentId != null) && (
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="px-4 py-2 text-xs font-medium border border-slate-900 dark:border-slate-200 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-md hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors disabled:bg-slate-400 disabled:border-slate-400 dark:disabled:bg-slate-700 dark:disabled:border-slate-700 dark:disabled:text-slate-500"
          >
            {generating
              ? (lang === "vi" ? "Đang tạo…" : "Generating…")
              : (lang === "vi" ? "Tạo Flashcard từ AI" : "Generate Flashcards")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 px-6 py-5">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handlePrev}
            disabled={index === 0}
            className="hover:text-slate-900 dark:hover:text-slate-100 disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
            title={lang === "vi" ? "Thẻ trước" : "Previous card"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          
          <span className="min-w-[40px] text-center font-medium tabular-nums">
            {labels.counter(index + 1, cards.length)}
          </span>

          <button
            type="button"
            onClick={handleNext}
            disabled={index === cards.length - 1}
            className="hover:text-slate-900 dark:hover:text-slate-100 disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
            title={lang === "vi" ? "Thẻ sau" : "Next card"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6"/></svg>
          </button>
        </div>
        
        <span className="font-medium">{flipped ? labels.back : labels.front}</span>
      </div>

      {/* Card surface — solid neutral, hairline border, no gradient. */}
      <button
        type="button"
        onClick={handleFlip}
        className="w-full text-left rounded-md border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors px-5 py-6 min-h-[140px] focus:outline-none focus:ring-1 focus:ring-slate-400 dark:focus:ring-slate-600"
      >
        <p className="text-base text-slate-900 dark:text-slate-100 leading-relaxed whitespace-pre-wrap">
          {flipped ? current.back_text : current.front_text}
        </p>
      </button>

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={handleFlip}
          className="text-xs font-medium text-slate-700 dark:text-slate-300 underline underline-offset-2"
        >
          {labels.flip}
        </button>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleRate(1)}
            className="px-3 py-1.5 text-xs font-medium border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-sm"
          >
            {labels.again}
          </button>
          <button
            type="button"
            onClick={() => handleRate(4)}
            className="px-3 py-1.5 text-xs font-medium border border-slate-900 dark:border-slate-200 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-200 rounded-sm"
          >
            {labels.good}
          </button>
        </div>
      </div>

      {/* Generate more flashcards */}
      {(ctx.nodeId != null || ctx.lessonId != null || ctx.contentId != null) && (
        <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="w-full py-2 text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-md transition-colors disabled:text-slate-400 dark:disabled:text-slate-600"
          >
            {generating
              ? (lang === "vi" ? "Đang tạo thêm…" : "Generating…")
              : (lang === "vi" ? "＋ Tạo thêm Flashcard từ AI" : "＋ Generate more Flashcards")}
          </button>
        </div>
      )}
    </div>
  );
}

export default FlashcardDeck;
