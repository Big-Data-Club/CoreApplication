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

  const lang = ctx.language ?? "vi";

  // Load 3–5 cards. Skip the network call entirely when no node_id is
  // attached — flashcards are always node-anchored upstream.
  useEffect(() => {
    if (ctx.nodeId == null) {
      setLoading(false);
      setCards([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await flashcardService.listFlashcardsByNode(
          ctx.courseId,
          ctx.nodeId as number,
        );
        if (cancelled) return;
        // Cap to 5 — the panel is meant for quick revision, not bulk study.
        setCards((res.data ?? []).slice(0, 5));
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
  }, [ctx.courseId, ctx.nodeId, lang]);

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
      <div className="px-6 py-10 text-sm text-slate-500 text-center">
        {labels.loading}
      </div>
    );
  }
  if (error) {
    return (
      <div className="px-6 py-10 text-sm text-red-600 text-center">
        {error}
      </div>
    );
  }
  if (cards.length === 0 || !current) {
    return (
      <div className="px-6 py-10 text-sm text-slate-500 text-center">
        {labels.empty}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 px-6 py-5">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-500">
        <span>{labels.counter(index + 1, cards.length)}</span>
        <span>{flipped ? labels.back : labels.front}</span>
      </div>

      {/* Card surface — solid neutral, hairline border, no gradient. */}
      <button
        type="button"
        onClick={handleFlip}
        className="w-full text-left rounded-md border border-slate-300 bg-slate-50 hover:bg-slate-100 transition-colors px-5 py-6 min-h-[140px] focus:outline-none focus:ring-1 focus:ring-slate-400"
      >
        <p className="text-base text-slate-900 leading-relaxed whitespace-pre-wrap">
          {flipped ? current.back_text : current.front_text}
        </p>
      </button>

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={handleFlip}
          className="text-xs font-medium text-slate-700 underline underline-offset-2"
        >
          {labels.flip}
        </button>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleRate(1)}
            className="px-3 py-1.5 text-xs font-medium border border-slate-300 text-slate-700 hover:bg-slate-100 rounded-sm"
          >
            {labels.again}
          </button>
          <button
            type="button"
            onClick={() => handleRate(4)}
            className="px-3 py-1.5 text-xs font-medium border border-slate-900 bg-slate-900 text-white hover:bg-slate-800 rounded-sm"
          >
            {labels.good}
          </button>
        </div>
      </div>
    </div>
  );
}

export default FlashcardDeck;
