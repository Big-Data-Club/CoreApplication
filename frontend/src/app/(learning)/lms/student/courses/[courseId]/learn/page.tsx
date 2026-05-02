"use client";

/**
 * Student Course — Learn Page
 * Route: /lms/student/courses/[courseId]/learn
 *
 * Displays the content viewer with prev/next navigation.
 * Consumes StudentCourseContext from the parent layout.
 *
 * ContentViewer (~30KB) is lazy-loaded since it's only rendered
 * when a content item is selected.
 */

import { useEffect, useRef, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import dynamic from "next/dynamic";
import {
  ArrowLeft, ChevronRight, BookOpen, BarChart3,
} from "lucide-react";

// Lazy-load the heavy content viewer
const ContentViewer = dynamic(
  () => import("@/components/lms/student/ContentViewer"),
  { ssr: false, loading: () => <div className="h-64 bg-slate-100 dark:bg-slate-800 rounded-2xl animate-pulse" /> },
);

import { Badge, ContentTypeBadge } from "@/components/lms/shared";
import { useStudentCourse } from "@/components/lms/student/StudentCourseContext";
import { Content, Section } from "@/types";

// ─── Prev / Next Navigation ─────────────────────────────────────────────────

function PrevNextButtons({
  sections, sectionContents, activeContent, onSelect,
}: {
  sections: Section[];
  sectionContents: Record<number, Content[]>;
  activeContent: Content;
  onSelect: (c: Content) => void;
}) {
  const flat = sections.flatMap(s => sectionContents[s.id] ?? []);
  const idx  = flat.findIndex(c => c.id === activeContent.id);
  const prev = idx > 0 ? flat[idx - 1] : null;
  const next = idx < flat.length - 1 ? flat[idx + 1] : null;

  return (
    <>
      {prev ? (
        <button
          className="flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          onClick={() => onSelect(prev)}
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="hidden sm:inline">Bài trước:</span>
          <span className="truncate max-w-[160px]">{prev.title}</span>
        </button>
      ) : <div />}

      {next && (
        <button
          className="flex items-center gap-2 text-sm font-semibold text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
          onClick={() => onSelect(next)}
        >
          <span className="truncate max-w-[160px]">{next.title}</span>
          <span className="hidden sm:inline">: Bài tiếp</span>
          <ChevronRight className="w-4 h-4" />
        </button>
      )}
    </>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function LearnPage() {
  const router = useRouter();
  const { courseId } = useParams<{ courseId: string }>();

  const {
    course, sections, sectionContents,
    activeContent, setActiveContent,
    completedIds, handleMarkComplete, markingComplete,
    toggleSection,
  } = useStudentCourse();

  // Timer ref for auto-complete
  const autoCompleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Auto-complete non-quiz mandatory content after 3s ──
  useEffect(() => {
    if (
      activeContent &&
      activeContent.is_mandatory &&
      !completedIds.has(activeContent.id) &&
      activeContent.type !== "QUIZ"
    ) {
      autoCompleteTimer.current = setTimeout(() => {
        handleMarkComplete(activeContent.id);
      }, 3000);
    }
    return () => {
      if (autoCompleteTimer.current) clearTimeout(autoCompleteTimer.current);
    };
  }, [activeContent?.id]); // eslint-disable-line

  // ── Handle content selection (clear timer) ──
  const handleSelect = useCallback((c: Content) => {
    if (autoCompleteTimer.current) clearTimeout(autoCompleteTimer.current);
    setActiveContent(c);
  }, [setActiveContent]);

  // ─── Render ───────────────────────────────────────────────────────────────

  if (!activeContent) {
    return (
      /* Welcome screen */
      <div className="flex flex-col items-center justify-center h-full py-24 text-center px-8">
        <div className="w-20 h-20 rounded-2xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center mb-6">
          <BookOpen className="w-10 h-10 text-blue-600 dark:text-blue-400" />
        </div>
        <h2 className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-2">
          Chào mừng đến với khóa học
        </h2>
        <p className="text-slate-600 dark:text-slate-400 max-w-sm mb-6">
          {course?.description ?? "Chọn một bài học ở bên trái để bắt đầu học."}
        </p>
        <div className="flex items-center gap-3">
          {sections.length > 0 && (
            <button
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold text-sm transition-all active:scale-95"
              onClick={() => toggleSection(sections[0].id)}
            >
              Bắt đầu học ngay
            </button>
          )}
          <button
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-all sm:hidden"
            onClick={() => router.push(`/lms/student/courses/${courseId}/stats`)}
          >
            <BarChart3 className="w-4 h-4" />
            Xem thống kê
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-4xl">
      {/* Badges */}
      <div className="flex items-center gap-2 mb-5">
        <ContentTypeBadge type={activeContent.type} />
        {activeContent.is_mandatory && <Badge variant="yellow">Bắt buộc</Badge>}
        {activeContent.is_mandatory && completedIds.has(activeContent.id) && (
          <Badge variant="green">✓ Đã hoàn thành</Badge>
        )}
      </div>

      {/* Title */}
      <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50 mb-2">
        {activeContent.title}
      </h2>
      {activeContent.description && (
        <p className="text-slate-600 dark:text-slate-400 mb-6">{activeContent.description}</p>
      )}
      <div className="border-t border-slate-200 dark:border-slate-800 mb-6" />

      {/* Viewer */}
      <ContentViewer
        content={activeContent}
        userRole="STUDENT"
        isCompleted={completedIds.has(activeContent.id)}
        courseId={courseId}
        onComplete={() => handleMarkComplete(activeContent.id)}
      />

      {/* Manual complete button (non-quiz mandatory, not yet done) */}
      {activeContent.is_mandatory &&
       !completedIds.has(activeContent.id) &&
       activeContent.type !== "QUIZ" && (
        <div className="mt-8 pt-6 border-t border-slate-200 dark:border-slate-800">
          <button
            onClick={() => handleMarkComplete(activeContent.id)}
            disabled={markingComplete}
            className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl font-semibold text-sm transition-all active:scale-95"
          >
            {markingComplete ? (
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            )}
            Đánh dấu đã hoàn thành
          </button>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-2">
            Hoặc nội dung sẽ tự động đánh dấu sau khi bạn xem đủ thời gian.
          </p>
        </div>
      )}

      {/* Prev / Next navigation */}
      <div className="mt-10 pt-6 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between gap-4">
        <PrevNextButtons
          sections={sections}
          sectionContents={sectionContents}
          activeContent={activeContent}
          onSelect={handleSelect}
        />
      </div>
    </div>
  );
}
