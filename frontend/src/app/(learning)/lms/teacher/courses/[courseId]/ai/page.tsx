"use client";

import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { useInView } from "@/hooks/useInView";

// Lazy-load both heavy panels — they are only needed on this specific tab
const AIQuizGenPanel = dynamic(
  () => import("@/components/lms/teacher/page/AIQuizGenPanel").then(m => ({ default: m.AIQuizGenPanel })),
  { ssr: false, loading: () => <div className="py-12 text-center text-sm text-slate-400">Đang tải AI Panel…</div> },
);

const AIHeatmapSection = dynamic(
  () => import("@/components/lms/AIHeatmapSection").then(m => ({ default: m.AIHeatmapSection })),
  { ssr: false, loading: () => <div className="h-64 bg-slate-100 dark:bg-slate-800 rounded-2xl animate-pulse" /> },
);

/**
 * /lms/teacher/courses/[courseId]/ai
 *
 * Two AI features on one page:
 *   1. AIQuizGenPanel  – knowledge node management + quiz generation + draft review
 *   2. AIHeatmapSection – class-level knowledge-gap heatmap (below fold → lazy)
 */
export default function CourseAIPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const id = Number(courseId);

  // Heatmap is below the fold — only load when scrolled into view
  const { ref: heatmapRef, isInView: heatmapVisible } = useInView();

  return (
    <div className="space-y-8">
      {/* Quiz generation + knowledge nodes */}
      <AIQuizGenPanel courseId={id} />

      {/* Class heatmap — lazy rendered on scroll */}
      <div ref={heatmapRef} className="border-t border-slate-200 dark:border-slate-800 pt-8">
        {heatmapVisible ? (
          <AIHeatmapSection courseId={id} role="teacher" />
        ) : (
          <div className="h-64 bg-slate-50 dark:bg-slate-900 rounded-2xl" />
        )}
      </div>
    </div>
  );
}
