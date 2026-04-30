"use client";

/**
 * AskAIDrawer.tsx
 *
 * Side drawer that appears when the student clicks the "Ask AI" tab in
 * the Quick Action Panel. The chatbot here is the same Mentor agent
 * used elsewhere in the app, but the request payload is augmented
 * with a `system_context` block containing the verbatim micro-lesson
 * body — so the model grounds every answer in what the student is
 * actually reading. The student never sees this hidden context; only
 * the model does.
 *
 * Each user prompt fires an `ask_ai` analytics event that the
 * heatmap aggregator counts toward the engagement component (10%).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { useAgentChat } from "@/hooks/useAgentChat";
import analyticsService from "@/services/analyticsService";
import type { MicroLessonContext } from "./types";

interface AskAIDrawerProps {
  ctx: MicroLessonContext;
  open: boolean;
  onClose: () => void;
}

export function AskAIDrawer({ ctx, open, onClose }: AskAIDrawerProps) {
  const { data: session } = useSession();
  const userId = session?.user
    ? Number((session.user as any).id || (session.user as any).userId)
    : undefined;

  const lang = ctx.language ?? "vi";

  // Stable systemContext object — build once per lesson so the hook's
  // dependency array doesn't churn on every keystroke.
  const systemContext = useMemo(
    () => ({
      lesson_id: ctx.lessonId,
      lesson_title: ctx.lessonTitle,
      node_id: ctx.nodeId ?? undefined,
      course_id: ctx.courseId,
      lesson_text: ctx.lessonText,
    }),
    [ctx.lessonId, ctx.lessonTitle, ctx.nodeId, ctx.courseId, ctx.lessonText],
  );

  const { messages, sendMessage, isStreaming, isThinking } = useAgentChat({
    agentType: "mentor",
    courseId: ctx.courseId,
    userId,
    systemContext,
  });

  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const labels = useMemo(
    () => ({
      title: lang === "vi" ? "Hỏi AI về bài học" : "Ask AI about this lesson",
      subtitle:
        lang === "vi"
          ? "AI đã được cung cấp toàn bộ nội dung bài học này."
          : "The AI has been given the full content of this lesson.",
      placeholder:
        lang === "vi"
          ? "Đặt câu hỏi về nội dung bài học…"
          : "Ask a question about this lesson…",
      send: lang === "vi" ? "Gửi" : "Send",
      empty:
        lang === "vi"
          ? "Bắt đầu bằng một câu hỏi về bài học bên trái."
          : "Start by asking a question about the lesson on the left.",
      thinking: lang === "vi" ? "AI đang suy nghĩ…" : "AI is thinking…",
      close: lang === "vi" ? "Đóng" : "Close",
    }),
    [lang],
  );

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    analyticsService.trackMicroInteraction({
      course_id: ctx.courseId,
      lesson_id: ctx.lessonId,
      node_id: ctx.nodeId ?? undefined,
      action_type: "ask_ai",
      payload: { length: trimmed.length },
    });

    sendMessage(trimmed);
    setInput("");
  }, [ctx.courseId, ctx.lessonId, ctx.nodeId, input, isStreaming, sendMessage]);

  // Auto-scroll on new content.
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // Lock body scroll while open + close on Escape.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = "unset";
      document.removeEventListener("keydown", handler);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop — flat neutral, no gradient. */}
      <div
        className="absolute inset-0 bg-slate-900/30 dark:bg-black/50"
        onClick={onClose}
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={labels.title}
        className="absolute right-0 top-0 h-full w-full max-w-md bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-lg flex flex-col"
      >
        <header className="flex items-start justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-50 tracking-tight">
              {labels.title}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{labels.subtitle}</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 truncate max-w-[18rem]">
              {ctx.lessonTitle}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-xs font-medium text-slate-700 dark:text-slate-300 underline underline-offset-2"
          >
            {labels.close}
          </button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
          {messages.length === 0 && !isStreaming ? (
            <p className="text-sm text-slate-500 dark:text-slate-400 text-center mt-12">
              {labels.empty}
            </p>
          ) : (
            <ul className="flex flex-col gap-4">
              {messages.map((m) => (
                <li
                  key={m.id}
                  className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
                >
                  <div
                    className={`max-w-[88%] text-sm leading-relaxed whitespace-pre-wrap rounded-md px-3 py-2 border ${
                      m.role === "user"
                        ? "bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-slate-900 dark:border-slate-100"
                        : "bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100 border-slate-200 dark:border-slate-700"
                    }`}
                  >
                    {m.content || (m.isStreaming ? "…" : "")}
                  </div>
                </li>
              ))}
              {isThinking && (
                <li className="text-xs text-slate-500 dark:text-slate-400">{labels.thinking}</li>
              )}
            </ul>
          )}
        </div>

        <footer className="border-t border-slate-200 dark:border-slate-800 px-5 py-3">
          <div className="flex items-end gap-2">
            <textarea
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={labels.placeholder}
              disabled={!userId}
              className="flex-1 resize-none border border-slate-300 dark:border-slate-700 rounded-sm bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-slate-100 px-3 py-2 focus:outline-none focus:border-slate-500 dark:focus:border-slate-400"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isStreaming || !userId}
              className="px-3 py-2 text-xs font-medium border border-slate-900 dark:border-slate-200 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-sm disabled:bg-slate-400 disabled:border-slate-400 dark:disabled:bg-slate-700 dark:disabled:border-slate-700 dark:disabled:text-slate-500"
            >
              {labels.send}
            </button>
          </div>
        </footer>
      </aside>
    </div>
  );
}

export default AskAIDrawer;
