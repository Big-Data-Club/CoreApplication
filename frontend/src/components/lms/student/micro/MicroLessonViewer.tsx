"use client";

/**
 * MicroLessonViewer.tsx
 *
 * Renders a single published micro-lesson and mounts the
 * `QuickActionPanel` at the bottom. This is the student-facing
 * counterpart to the teacher's MicroLessonsDrawer editor.
 *
 * The component is intentionally thin: data fetching is the parent
 * page's job (so this works the same way whether the lesson is
 * embedded inline or shown in a dedicated route). The parent passes
 * the resolved lesson + course context.
 */
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { QuickActionPanel } from "./QuickActionPanel";
import type { MicroLessonContext } from "./types";

interface MicroLessonViewerProps {
  ctx: MicroLessonContext;
  /** Optional preamble (e.g. lesson summary or objectives list). */
  summary?: string | null;
  objectives?: string[] | null;
  estimatedMinutes?: number;
}

export function MicroLessonViewer({
  ctx,
  summary,
  objectives,
  estimatedMinutes,
}: MicroLessonViewerProps) {
  return (
    <article className="border border-slate-200 bg-white">
      <header className="px-6 py-5 border-b border-slate-200">
        <h1 className="text-lg font-semibold text-slate-900 tracking-tight">
          {ctx.lessonTitle}
        </h1>
        {typeof estimatedMinutes === "number" && estimatedMinutes > 0 && (
          <p className="text-xs text-slate-500 mt-1">
            {ctx.language === "en"
              ? `Estimated read: ${estimatedMinutes} min`
              : `Thời gian đọc: ${estimatedMinutes} phút`}
          </p>
        )}
      </header>

      {(summary || (objectives && objectives.length > 0)) && (
        <section className="px-6 py-4 border-b border-slate-200 bg-slate-50">
          {summary && (
            <p className="text-sm text-slate-700 leading-relaxed">{summary}</p>
          )}
          {objectives && objectives.length > 0 && (
            <ul className="mt-3 list-disc list-inside text-sm text-slate-700 space-y-1">
              {objectives.map((obj, i) => (
                <li key={i}>{obj}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <div className="px-6 py-6 prose prose-slate max-w-none">
        <MarkdownRenderer content={ctx.lessonText} />
      </div>

      <QuickActionPanel ctx={ctx} />
    </article>
  );
}

export default MicroLessonViewer;
