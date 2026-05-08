"use client";

/**
 * Student Course Detail Layout
 * Route: /lms/student/courses/[courseId]
 *
 * Provides:
 *  - Sticky header with course title + tab switcher (Học tập / Thống kê)
 *  - Desktop sidebar (sections / progress)
 *  - Mobile sidebar drawer
 *  - StudentCourseContext for child pages
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import {
  ChevronDown, ChevronRight, Menu, X,
  Play, FileText, Image as ImageIcon, HelpCircle,
  MessageSquare, Megaphone, File as FileIcon, BookOpen,
  BarChart3, CheckCircle2,
} from "lucide-react";

import lmsService from "@/services/lmsService";
import progressService, { CourseProgress, ProgressDetailItem } from "@/services/progressService";

import { ProgressBar, PageLoader } from "@/components/lms/shared";
import { BreadcrumbNav, type BreadcrumbItem } from "@/components/lms/BreadcrumbNav";
import { StudentCourseContext } from "@/components/lms/student/StudentCourseContext";
import { Content, Course, Section } from "@/types";
import { cn } from "@/lib/utils";
import { useSetPageContext } from "@/hooks/usePageContext";
import { ChatFAB } from "@/components/lms/agent/ChatFAB";

// ─── Content type icon map ────────────────────────────────────────────────────

const CONTENT_ICON: Record<string, React.ReactNode> = {
  VIDEO: <Play className="w-3.5 h-3.5" />,
  DOCUMENT: <FileText className="w-3.5 h-3.5" />,
  IMAGE: <ImageIcon className="w-3.5 h-3.5" />,
  TEXT: <FileText className="w-3.5 h-3.5" />,
  QUIZ: <HelpCircle className="w-3.5 h-3.5" />,
  FORUM: <MessageSquare className="w-3.5 h-3.5" />,
  ANNOUNCEMENT: <Megaphone className="w-3.5 h-3.5" />,
};

// ─── Tab definitions ──────────────────────────────────────────────────────────

const TABS = [
  { id: "learn", label: "Học tập", path: "/learn", icon: null },
  { id: "stats", label: "Thống kê", path: "/stats", icon: <BarChart3 className="w-3.5 h-3.5" /> },
];

// ─────────────────────────────────────────────────────────────────────────────
// SIDEBAR SECTION
// ─────────────────────────────────────────────────────────────────────────────

interface SidebarSectionProps {
  section: Section;
  index: number;
  contents: Content[];
  loading: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  activeContentId: number | null;
  onSelect: (c: Content) => void;
  completedIds: Set<number>;
}

function SidebarSection({
  section, index, contents, loading,
  isExpanded, onToggle, activeContentId, onSelect,
  completedIds,
}: SidebarSectionProps) {
  const mandatoryCount = contents.filter(c => c.is_mandatory).length;
  const completedMandatory = contents.filter(c => c.is_mandatory && completedIds.has(c.id)).length;

  return (
    <div className="border-b border-slate-100 dark:border-slate-800 last:border-b-0">
      {/* Section header */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
        onClick={onToggle}
      >
        <div className="w-6 h-6 rounded-full bg-blue-50 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-xs font-bold flex-shrink-0 border border-blue-200 dark:border-blue-800">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">{section.title}</p>
          {contents.length > 0 && (
            <p className="text-xs text-slate-500 mt-0.5">
              {mandatoryCount > 0
                ? `${completedMandatory}/${mandatoryCount} bắt buộc`
                : `${contents.length} nội dung`}
            </p>
          )}
        </div>
        {isExpanded
          ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
          : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
      </button>

      {/* Content items */}
      {isExpanded && (
        <div className="pb-1">
          {loading && !contents.length ? (
            <div className="px-4 py-3 space-y-2">
              {[0, 1, 2].map(i => (
                <div key={i} className="h-8 bg-slate-100 dark:bg-slate-800 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : contents.length === 0 ? (
            <p className="px-4 py-3 text-xs text-slate-400">Chưa có nội dung</p>
          ) : (
            contents.map((c, i) => {
              const isActive = c.id === activeContentId;
              const isDone = completedIds.has(c.id);
              return (
                <button
                  key={c.id}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-4 py-2.5 text-left transition-colors",
                    isActive
                      ? "bg-blue-50 dark:bg-blue-900/20 border-r-2 border-blue-600"
                      : "hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  )}
                  onClick={() => onSelect(c)}
                >
                  {/* Content type icon */}
                  <span className={cn(
                    "flex-shrink-0",
                    isActive ? "text-blue-600 dark:text-blue-400" : "text-slate-400 dark:text-slate-500"
                  )}>
                    {CONTENT_ICON[c.type] ?? <FileIcon className="w-3.5 h-3.5" />}
                  </span>

                  {/* Title */}
                  <span className={cn(
                    "text-sm flex-1 truncate",
                    isActive
                      ? "font-semibold text-blue-700 dark:text-blue-300"
                      : "text-slate-700 dark:text-slate-300"
                  )}>
                    {i + 1}. {c.title}
                  </span>

                  {/* Status dot */}
                  <span className="flex-shrink-0 w-4 flex items-center justify-center">
                    {isDone ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    ) : c.is_mandatory ? (
                      <span className="w-1.5 h-1.5 rounded-full bg-orange-400" title="Bắt buộc" />
                    ) : null}
                  </span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN LAYOUT
// ─────────────────────────────────────────────────────────────────────────────

export default function StudentCourseDetailLayout({ children }: { children: React.ReactNode }) {
  const { courseId } = useParams<{ courseId: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const id = Number(courseId);
  const basePath = `/lms/student/courses/${id}`;

  // ── Core state ──
  const [course, setCourse] = useState<Course | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [sectionContents, setSectionContents] = useState<Record<number, Content[]>>({});
  const [loadingSection, setLoadingSection] = useState<Record<number, boolean>>({});
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [activeContent, setActiveContent] = useState<Content | null>(null);
  const [loadingPage, setLoadingPage] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // ── Progress state ──
  const [progress, setProgress] = useState<CourseProgress | null>(null);
  const [completedIds, setCompletedIds] = useState<Set<number>>(new Set());
  const [progressDetail, setProgressDetail] = useState<ProgressDetailItem[]>([]);
  const [markingComplete, setMarkingComplete] = useState(false);

  // ─── Load progress ────────────────────────────────────────────────────────

  const loadProgress = useCallback(async () => {
    try {
      const [prog, detail] = await Promise.all([
        progressService.getMyCourseProgress(id),
        progressService.getMyCourseProgressDetail(id),
      ]);
      if (prog) {
        setProgress(prog);
        setCompletedIds(new Set(prog.completed_content_ids ?? []));
      }
      setProgressDetail(detail ?? []);
    } catch {
      // Progress API may not be available yet — degrade gracefully
    }
  }, [id]);

  // ─── Load course + sections ───────────────────────────────────────────────

  useEffect(() => {
    (async () => {
      try {
        const [courseRes, sectionsRes] = await Promise.all([
          lmsService.getCourse(id),
          lmsService.listSections(id),
        ]);
        setCourse(courseRes?.data ?? null);
        const secs: Section[] = sectionsRes?.data ?? [];
        setSections(secs);

        if (secs.length > 0) {
          const allIds = secs.map(s => s.id);
          setExpanded(new Set(allIds));
          // Prefetch all contents (parallel, will be cached by loadSectionContentsInner)
          allIds.forEach(sid => loadSectionContentsInner(sid));

          // Auto-select the first content of the first section
          loadSectionContentsInner(secs[0].id, true);
        }
      } catch {
        router.back();
      } finally {
        setLoadingPage(false);
      }
    })();
    loadProgress();
  }, [id]); // eslint-disable-line

  // ─── Load section contents ────────────────────────────────────────────────

  const loadSectionContentsInner = useCallback(async (sectionId: number, autoSelect = false) => {
    if (sectionContents[sectionId]) {
      if (autoSelect && !activeContent) {
        const first = sectionContents[sectionId][0];
        if (first) setActiveContent(first);
      }
      return;
    }
    setLoadingSection(prev => ({ ...prev, [sectionId]: true }));
    try {
      const res = await lmsService.listContent(sectionId);
      const items: Content[] = res?.data ?? [];
      setSectionContents(prev => ({ ...prev, [sectionId]: items }));
      if (autoSelect && !activeContent && items.length > 0) {
        setActiveContent(items[0]);
      }
    } finally {
      setLoadingSection(prev => ({ ...prev, [sectionId]: false }));
    }
  }, [sectionContents, activeContent]);

  const loadSectionContents = useCallback((sectionId: number, autoSelect = false) => {
    loadSectionContentsInner(sectionId, autoSelect);
  }, [loadSectionContentsInner]);

  const toggleSection = useCallback((sectionId: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
        loadSectionContentsInner(sectionId);
      }
      return next;
    });
  }, [loadSectionContentsInner]);

  // ─── Mark content complete ────────────────────────────────────────────────

  const handleMarkComplete = useCallback(async (contentId: number) => {
    if (completedIds.has(contentId) || markingComplete) return;
    setMarkingComplete(true);
    try {
      await progressService.markContentComplete(contentId);
      setCompletedIds(prev => new Set([...prev, contentId]));
      await loadProgress();
    } catch {
      // fail silently; will retry on next interaction
    } finally {
      setMarkingComplete(false);
    }
  }, [completedIds, markingComplete, loadProgress]);

  // ─── Select content (navigate to learn page) ─────────────────────────────

  const handleSelectContent = useCallback((c: Content) => {
    setActiveContent(c);
    setSidebarOpen(false);
    // Navigate to learn page if not already there
    if (!pathname.endsWith("/learn")) {
      router.push(`${basePath}/learn`);
    }
  }, [pathname, basePath, router]);

  // ─── Derived progress numbers ─────────────────────────────────────────────

  const totalMandatory = progress?.total_mandatory
    ?? Object.values(sectionContents).flat().filter(c => c.is_mandatory).length;
  const completedCount = progress?.completed_count ?? completedIds.size;
  const progressPct = totalMandatory > 0 ? Math.round((completedCount / totalMandatory) * 100) : 0;

  // ─── Active tab ───────────────────────────────────────────────────────────
  const activeTab = TABS.find(tab => pathname.includes(tab.path)) || TABS[0];
  const activeTabId = activeTab.id;

  // ─── Breadcrumb items ─────────────────────────────────────────────────────
  const breadcrumbItems: BreadcrumbItem[] = [
    { label: "Học tập", href: "/lms/student" },
    {
      label: loadingPage ? "..." : (course?.title ?? "Khóa học"),
      href: `${basePath}/learn`,
    },
    ...(activeTabId !== "learn" ? [{ label: activeTab.label }] : []),
  ];

  // ─── Context value ────────────────────────────────────────────────────────

  const contextValue = useMemo(() => ({
    course,
    sections,
    courseId: id,
    activeContent,
    setActiveContent: handleSelectContent,
    sectionContents,
    loadSectionContents,
    loadingSection,
    expanded,
    toggleSection,
    sidebarOpen,
    setSidebarOpen,
    completedIds,
    handleMarkComplete,
    markingComplete,
    progress,
    progressDetail,
    loadProgress,
  }), [
    course, sections, id,
    activeContent, handleSelectContent,
    sectionContents, loadSectionContents, loadingSection,
    expanded, toggleSection,
    sidebarOpen,
    completedIds, handleMarkComplete, markingComplete,
    progress, progressDetail, loadProgress,
  ]);

  // ── Push page context for AI sidebar ───────────────────────────────────────

  const { setPageContext, clearPageContext } = useSetPageContext();

  useEffect(() => {
    if (!course) return;
    setPageContext({
      pageType: activeContent ? "lesson" : "course_detail",
      courseId: id,
      courseName: course.title,
      contentId: activeContent?.id,
      contentTitle: activeContent?.title,
    });
    return () => clearPageContext();
  }, [course, activeContent, id, setPageContext, clearPageContext]);

  if (loadingPage) return <PageLoader message="Đang tải khóa học..." />;

  // ─── Sidebar JSX ──────────────────────────────────────────────────────────

  const SidebarContent = (
    <div className="h-full flex flex-col">
      {/* Progress header */}
      <div className="px-4 pt-5 pb-4 border-b border-slate-200 dark:border-slate-800">
        <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
          Tiến độ học tập
        </p>
        <ProgressBar
          value={completedCount}
          max={totalMandatory || 1}
          color="blue"
          showPercent={false}
          className="mb-1"
        />
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {completedCount}/{totalMandatory} bài bắt buộc
          {totalMandatory > 0 && ` · ${progressPct}%`}
        </p>
      </div>

      {/* Section list */}
      <div className="flex-1 overflow-y-auto">
        {sections.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <BookOpen className="w-8 h-8 text-slate-300 dark:text-slate-700 mx-auto mb-2" />
            <p className="text-sm text-slate-400">Khóa học chưa có nội dung</p>
          </div>
        ) : (
          sections.map((sec, i) => (
            <SidebarSection
              key={sec.id}
              section={sec}
              index={i}
              contents={sectionContents[sec.id] ?? []}
              loading={!!loadingSection[sec.id]}
              isExpanded={expanded.has(sec.id)}
              onToggle={() => toggleSection(sec.id)}
              activeContentId={activeContent?.id ?? null}
              onSelect={handleSelectContent}
              completedIds={completedIds}
            />
          ))
        )}
      </div>
    </div>
  );

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <StudentCourseContext.Provider value={contextValue}>
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex flex-col">

        {/* ── Header ── */}
        <header className="sticky top-0 z-30 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 shadow-sm">
          <div className="max-w-screen-2xl mx-auto px-4 h-14 flex items-center gap-3">
            <BreadcrumbNav items={breadcrumbItems} className="flex-1 min-w-0" />

            {/* Tab switcher pill */}
            <div className="hidden sm:flex items-center gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1 flex-shrink-0">
              {TABS.map(tab => (
                <Link
                  key={tab.id}
                  href={`${basePath}${tab.path}`}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
                    activeTabId === tab.id
                      ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-50 shadow-sm"
                      : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100"
                  )}
                >
                  {tab.icon}
                  {tab.label}
                </Link>
              ))}
            </div>

            {/* Mobile: sidebar toggle */}
            <button
              className="lg:hidden p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu className="w-5 h-5" />
            </button>
          </div>

          {/* Mobile tab bar */}
          <div className="sm:hidden flex items-center gap-1 px-4 pb-2">
            {TABS.map(tab => (
              <Link
                key={tab.id}
                href={`${basePath}${tab.path}`}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
                  activeTabId === tab.id
                    ? "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400"
                    : "text-slate-600 dark:text-slate-400"
                )}
              >
                {tab.icon}
                {tab.label}
              </Link>
            ))}
          </div>
        </header>

        {/* ── Body ── */}
        <div className="flex-1 max-w-screen-2xl mx-auto w-full flex overflow-hidden">

          {/* Desktop sidebar */}
          <aside className="hidden lg:flex flex-col w-72 xl:w-80 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex-shrink-0 sticky top-14 h-[calc(100vh-3.5rem)] overflow-hidden">
            {SidebarContent}
          </aside>

          {/* Mobile sidebar drawer */}
          {sidebarOpen && (
            <div className="lg:hidden fixed inset-0 z-40 flex">
              <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
              <aside className="relative w-80 max-w-[85vw] bg-white dark:bg-slate-900 h-full overflow-hidden flex flex-col">
                <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800">
                  <span className="font-bold text-slate-900 dark:text-slate-50">Nội dung khóa học</span>
                  <button onClick={() => setSidebarOpen(false)} className="p-1 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
                    <X className="w-5 h-5" />
                  </button>
                </div>
                {SidebarContent}
              </aside>
            </div>
          )}

          {/* ── Main content (child pages) ── */}
          <main className="flex-1 overflow-y-auto min-w-0">
            {children}
          </main>
        </div>
        {/* ── AI Chat FAB — only visible within a course ── */}
        <ChatFAB />
      </div>
    </StudentCourseContext.Provider>
  );
}
