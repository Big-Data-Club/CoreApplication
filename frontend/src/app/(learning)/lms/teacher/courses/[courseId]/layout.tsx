"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Edit3 } from "lucide-react";
import lmsService from "@/services/lmsService";
import { BreadcrumbNav, type BreadcrumbItem } from "@/components/lms/BreadcrumbNav";
import { Badge, Spinner } from "@/components/lms/shared";
import { Course } from "@/types";
import { cn } from "@/lib/utils";
import { useSetPageContext } from "@/hooks/usePageContext";
import { ChatFAB } from "@/components/lms/agent/ChatFAB";

// Lazy-load modal — only needed when user clicks "Chỉnh sửa"
const EditCourseModal = dynamic(
  () => import("@/components/lms/teacher/EditCourseModal").then(m => ({ default: m.EditCourseModal })),
  { ssr: false },
);

// ─── Tab definitions ─────────────────────────────────────────────────────────

const COURSE_TABS = [
  { id: "overview", label: "Tổng quan", path: "/overview" },
  { id: "content", label: "Nội dung", path: "/content" },
  { id: "learners", label: "Học viên", path: "/learners" },
  { id: "students", label: "Tiến độ học tập", path: "/students" },
  { id: "ai", label: "🤖 AI", path: "/ai" },
];

// ─── Layout ───────────────────────────────────────────────────────────────────

export default function CourseDetailLayout({ children }: { children: React.ReactNode }) {
  const { courseId } = useParams<{ courseId: string }>();
  const pathname = usePathname();
  const id = Number(courseId);

  const [course, setCourse] = useState<Course | null>(null);
  const [loading, setLoading] = useState(true);
  const [showEditModal, setShowEditModal] = useState(false);

  const basePath = `/lms/teacher/courses/${id}`;

  const loadCourse = useCallback(async () => {
    try {
      const res = await lmsService.getCourse(id);
      setCourse(res?.data ?? null);
    } catch { }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { loadCourse(); }, [loadCourse]);

  // ── Determine active tab ────────────────────────────────────────────────────
  const activeTab =
    COURSE_TABS.find(tab => {
      const fullPath = `${basePath}${tab.path}`;
      if (tab.id === "content") return pathname.startsWith(fullPath);
      return pathname === fullPath;
    }) ??
    // Fallback: if at basePath itself (before redirect kicks in), treat as overview
    COURSE_TABS[0];

  // ── Breadcrumb items ────────────────────────────────────────────────────────
  const breadcrumbItems: BreadcrumbItem[] = [
    { label: "Khóa học", href: "/lms/teacher/courses" },
    {
      label: loading ? "..." : (course?.title ?? "Khóa học"),
      href: `${basePath}/overview`,
    },
    ...(activeTab.id !== "overview" ? [{ label: activeTab.label }] : []),
  ];

  // ── Push page context for AI sidebar ─────────────────────────────────────

  const { setPageContext, clearPageContext } = useSetPageContext();

  useEffect(() => {
    if (!course) return;
    setPageContext({
      pageType: "course_detail",
      courseId: id,
      courseName: course.title,
    });
    return () => clearPageContext();
  }, [course, id, setPageContext, clearPageContext]);

  return (
    <div className="space-y-4">
      {/* ── Breadcrumb ───────────────────────────────────────────────────── */}
      <BreadcrumbNav items={breadcrumbItems} />

      {/* ── Course header card ───────────────────────────────────────────── */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm p-4">
        {loading ? (
          <div className="flex items-center gap-3">
            <Spinner className="w-4 h-4 border-2" />
            <span className="text-sm text-slate-500 dark:text-slate-400">
              Đang tải khóa học…
            </span>
          </div>
        ) : course ? (
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0 flex-1">
              {/* Status badges */}
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <Badge variant={course.status === "PUBLISHED" ? "green" : "yellow"}>
                  {course.status === "PUBLISHED" ? "Đã xuất bản" : "Nháp"}
                </Badge>
                {course.category && <Badge variant="gray">{course.category}</Badge>}
                {course.level && <Badge variant="blue">{course.level}</Badge>}
              </div>

              <h1 className="text-xl font-extrabold text-slate-900 dark:text-slate-50 leading-tight truncate">
                {course.title}
              </h1>

              {course.description && (
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-1">
                  {course.description}
                </p>
              )}
            </div>

            {/* Edit button */}
            <button
              onClick={() => setShowEditModal(true)}
              className="
                flex items-center gap-1.5 px-3 py-1.5
                text-sm font-medium
                text-slate-600 dark:text-slate-400
                border border-slate-300 dark:border-slate-700
                rounded-xl
                hover:bg-slate-50 dark:hover:bg-slate-800
                active:scale-95 transition-all duration-200
                flex-shrink-0
              "
            >
              <Edit3 className="w-3.5 h-3.5" />
              Chỉnh sửa
            </button>
          </div>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Không tìm thấy khóa học.
          </p>
        )}
      </div>

      {/* ── Tab card ─────────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {/* Tab navigation */}
        <div className="flex gap-0.5 px-4 pt-3 border-b border-slate-200 dark:border-slate-800 overflow-hidden">
          {COURSE_TABS.map(tab => {
            const href = `${basePath}${tab.path}`;
            const isActive = activeTab.id === tab.id;
            return (
              <Link
                key={tab.id}
                href={href}
                className={cn(
                  "px-4 py-2.5 text-sm font-medium whitespace-nowrap rounded-t-lg -mb-px border-b-2 transition-all duration-200",
                  isActive
                    ? "border-blue-600 text-blue-600 dark:text-blue-400 bg-blue-50/60 dark:bg-blue-900/10"
                    : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-100 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                )}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>

        {/* Tab content */}
        <div className="p-6">
          {children}
        </div>
      </div>

      {/* ── Edit course modal ─────────────────────────────────────────────── */}
      {showEditModal && course && (
        <EditCourseModal
          course={course}
          onClose={() => setShowEditModal(false)}
          onSuccess={() => { setShowEditModal(false); loadCourse(); }}
        />
      )}

      {/* ── AI Chat FAB — only visible within a course ── */}
      <ChatFAB />
    </div>
  );
}
