"use client";

/**
 * ContentTab
 *
 * Manages the full section → content tree for a course.
 * Extracted from the old monolithic [courseId]/page.tsx so it can be
 * mounted as a standalone page and independently loaded/refreshed.
 *
 * Props:
 *   courseId          – parent course id
 *   sections          – pre-fetched sections list (owner manages refresh)
 *   onSectionsChange  – called after any section create/update/delete
 *
 * Heavy modals are lazy-loaded via next/dynamic so the initial chunk
 * stays lean. Each modal is only fetched when the user triggers it.
 */

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  Plus, Edit3, Upload, Eye, Trash2,
  Play, FileText, HelpCircle, MessageSquare,
  Megaphone, Image as ImageIcon, File,
  ChevronDown, ChevronRight, Sparkles, History,
} from "lucide-react";
import lmsService from "@/services/lmsService";
import { SectionModal } from "@/components/lms/teacher/SectionModal";
import { AIIndexButton } from "@/components/lms/teacher/ai/AIIndexButton";
import { AIIndexPollerProvider } from "@/hooks/useAIIndexPoller";
import {
  Badge, ContentTypeBadge, EmptyState, PrimaryBtn, Spinner,
} from "@/components/lms/shared";
import { Content, Section } from "@/types";

// ─── Lazy-loaded heavy modals (only fetched when opened) ──────────────────────

const ContentViewer = dynamic(
  () => import("@/components/lms/student/ContentViewer"),
  { ssr: false },
);

const ContentModal = dynamic(
  () => import("@/components/lms/teacher/ContentModal").then(m => ({ default: m.default })),
  { ssr: false },
);

const EditContentModal = dynamic(
  () => import("@/components/lms/teacher/EditContentModal").then(m => ({ default: m.default })),
  { ssr: false },
);

const BulkUploadModal = dynamic(
  () => import("@/components/lms/teacher/upload/BulkUploadModal").then(m => ({ default: m.default })),
  { ssr: false },
);

const GenerateMicroLessonsModal = dynamic(
  () => import("@/components/lms/teacher/micro/GenerateMicroLessonsModal").then(m => ({ default: m.GenerateMicroLessonsModal })),
  { ssr: false },
);

const MicroLessonsDrawer = dynamic(
  () => import("@/components/lms/teacher/micro/MicroLessonsDrawer").then(m => ({ default: m.MicroLessonsDrawer })),
  { ssr: false },
);

const MicroLessonHistoryModal = dynamic(
  () => import("@/components/lms/teacher/micro/MicroLessonHistoryModal").then(m => ({ default: m.MicroLessonHistoryModal })),
  { ssr: false },
);

// ─── Content type icon map ────────────────────────────────────────────────────

const CONTENT_ICON: Record<string, React.ReactNode> = {
  VIDEO:        <Play className="w-3.5 h-3.5" />,
  DOCUMENT:     <FileText className="w-3.5 h-3.5" />,
  IMAGE:        <ImageIcon className="w-3.5 h-3.5" />,
  TEXT:         <FileText className="w-3.5 h-3.5" />,
  QUIZ:         <HelpCircle className="w-3.5 h-3.5" />,
  FORUM:        <MessageSquare className="w-3.5 h-3.5" />,
  ANNOUNCEMENT: <Megaphone className="w-3.5 h-3.5" />,
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface ContentTabProps {
  courseId: number;
  sections: Section[];
  onSectionsChange: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ContentTab({ courseId, sections, onSectionsChange }: ContentTabProps) {
  const [expanded, setExpanded]   = useState<Set<number>>(new Set());
  const [sectionContents, setSectionContents] = useState<Record<number, Content[]>>({});
  const [loadingContent, setLoadingContent]   = useState<Record<number, boolean>>({});

  // Modal state
  const [showSectionModal, setShowSectionModal]       = useState(false);
  const [editingSection, setEditingSection]           = useState<Section | null>(null);
  const [showContentModal, setShowContentModal]       = useState(false);
  const [showBulkModal, setShowBulkModal]             = useState(false);
  const [showEditContentModal, setShowEditContentModal] = useState(false);
  const [showContentViewer, setShowContentViewer]     = useState(false);
  const [selectedSectionId, setSelectedSectionId]     = useState<number | null>(null);
  const [editingContent, setEditingContent]           = useState<Content | null>(null);
  const [viewingContent, setViewingContent]           = useState<Content | null>(null);

  // Deletion in-progress
  const [deletingSection, setDeletingSection] = useState<number | null>(null);
  const [deletingContent, setDeletingContent] = useState<number | null>(null);

  // Micro-lesson modal / drawer state
  const [showMicroModal, setShowMicroModal]       = useState(false);
  const [showMicroHistoryModal, setShowMicroHistoryModal] = useState(false);
  const [microPresetContentId, setMicroPresetContentId] = useState<number | undefined>();
  const [microPresetSectionId, setMicroPresetSectionId] = useState<number | undefined>();
  const [activeMicroJobId, setActiveMicroJobId]   = useState<number | null>(null);

  // ── Content loading ─────────────────────────────────────────────────────────

  const loadContents = useCallback(async (sectionId: number) => {
    if (sectionContents[sectionId]) return;
    setLoadingContent(prev => ({ ...prev, [sectionId]: true }));
    try {
      const res = await lmsService.listContent(sectionId);
      setSectionContents(prev => ({ ...prev, [sectionId]: res?.data ?? [] }));
    } finally {
      setLoadingContent(prev => ({ ...prev, [sectionId]: false }));
    }
  }, [sectionContents]);

  // Initial expansion: expand all when sections are loaded
  useEffect(() => {
    if (sections.length > 0 && expanded.size === 0) {
      const allIds = sections.map(s => s.id);
      setExpanded(new Set(allIds));
      allIds.forEach(id => loadContents(id));
    }
  }, [sections, loadContents]); // eslint-disable-line

  const reloadSectionContent = useCallback(async (sectionId: number) => {
    setLoadingContent(prev => ({ ...prev, [sectionId]: true }));
    try {
      const res = await lmsService.listContent(sectionId);
      setSectionContents(prev => ({ ...prev, [sectionId]: res?.data ?? [] }));
    } finally {
      setLoadingContent(prev => ({ ...prev, [sectionId]: false }));
    }
  }, []);

  // ── Toggle section expand ───────────────────────────────────────────────────

  const toggle = (id: number) => {
    setExpanded(prev => {
      const n = new Set(prev);
      if (n.has(id)) { n.delete(id); } else { n.add(id); loadContents(id); }
      return n;
    });
  };

  // ── Delete handlers ─────────────────────────────────────────────────────────

  const deleteSection = async (id: number) => {
    if (!confirm("Xóa chương này? Tất cả nội dung bên trong cũng sẽ bị xóa.")) return;
    setDeletingSection(id);
    try { await lmsService.deleteSection(id); onSectionsChange(); }
    finally { setDeletingSection(null); }
  };

  const deleteContent = async (contentId: number, sectionId: number) => {
    if (!confirm("Xóa nội dung này?")) return;
    setDeletingContent(contentId);
    try {
      await lmsService.deleteContent(contentId);
      setSectionContents(prev => ({
        ...prev,
        [sectionId]: (prev[sectionId] ?? []).filter(c => c.id !== contentId),
      }));
    } finally { setDeletingContent(null); }
  };

  // ── onIndexed callback for the batch poller ─────────────────────────────────
  const handleContentIndexed = useCallback((contentId: number) => {
    // Find which section this content belongs to and reload it
    for (const [sectionId, contents] of Object.entries(sectionContents)) {
      if ((contents as Content[]).some(c => c.id === contentId)) {
        reloadSectionContent(Number(sectionId));
        break;
      }
    }
  }, [sectionContents, reloadSectionContent]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <AIIndexPollerProvider onIndexed={handleContentIndexed}>
    <div className="space-y-4">
      {/* Top action bar */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-sm text-slate-500 dark:text-slate-500">
          {sections.length} chương
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowMicroHistoryModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors"
            title="Xem lại các tiến trình tạo bài học micro"
          >
            <History className="w-4 h-4" />
            Lịch sử Job
          </button>
          <button
            onClick={() => {
              setMicroPresetContentId(undefined);
              setMicroPresetSectionId(undefined);
              setShowMicroModal(true);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-violet-600 hover:bg-violet-700 text-white transition-colors"
            title="AI sẽ phân tích tài liệu và chia thành các bài học ngắn ~5 phút"
          >
            <Sparkles className="w-4 h-4" />
            Tạo bài học micro
          </button>
          <PrimaryBtn
            size="sm"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => { setEditingSection(null); setShowSectionModal(true); }}
          >
            Thêm chương
          </PrimaryBtn>
        </div>
      </div>

      {/* Empty state */}
      {sections.length === 0 ? (
        <EmptyState
          icon={<FileText className="w-10 h-10" />}
          title="Chưa có chương nào"
          description="Tạo chương đầu tiên để bắt đầu thêm nội dung."
          action={
            <PrimaryBtn
              size="sm"
              icon={<Plus className="w-4 h-4" />}
              onClick={() => setShowSectionModal(true)}
            >
              Tạo chương đầu tiên
            </PrimaryBtn>
          }
        />
      ) : (
        <div className="space-y-3">
          {sections.map((sec, i) => {
            const isExpanded  = expanded.has(sec.id);
            const contents    = sectionContents[sec.id] ?? [];
            const isLoadingC  = loadingContent[sec.id];

            return (
              <div
                key={sec.id}
                className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900"
              >
                {/* ── Section header ── */}
                <div
                  className="flex items-center gap-3 px-5 py-4 bg-slate-50 dark:bg-slate-800/50 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  onClick={() => toggle(sec.id)}
                >
                  {/* Index badge */}
                  <div className="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-xs font-bold flex-shrink-0 border border-blue-200 dark:border-blue-800">
                    {i + 1}
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-slate-900 dark:text-slate-50 truncate">
                      {sec.title}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {isExpanded
                        ? `${contents.length} nội dung`
                        : sec.description || "Nhấn để xem nội dung"}
                    </p>
                  </div>

                  {/* Section actions */}
                  <div
                    className="flex items-center gap-1"
                    onClick={e => e.stopPropagation()}
                  >
                    {/* Add content */}
                    <button
                      title="Thêm nội dung"
                      className="p-1.5 rounded-lg hover:bg-white dark:hover:bg-slate-700 text-slate-500 transition-colors"
                      onClick={() => { setSelectedSectionId(sec.id); setShowContentModal(true); }}
                    >
                      <Plus className="w-4 h-4" />
                    </button>

                    {/* Bulk upload */}
                    <button
                      title="Upload nhiều file"
                      className="p-1.5 rounded-lg hover:bg-white dark:hover:bg-slate-700 text-slate-500 transition-colors"
                      onClick={() => { setSelectedSectionId(sec.id); setShowBulkModal(true); }}
                    >
                      <Upload className="w-4 h-4" />
                    </button>

                    {/* Edit section */}
                    <button
                      title="Sửa chương"
                      className="p-1.5 rounded-lg hover:bg-white dark:hover:bg-slate-700 text-slate-500 transition-colors"
                      onClick={() => { setEditingSection(sec); setShowSectionModal(true); }}
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>

                    {/* Delete section */}
                    <button
                      title="Xóa chương"
                      disabled={deletingSection === sec.id}
                      className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors"
                      onClick={() => deleteSection(sec.id)}
                    >
                      {deletingSection === sec.id
                        ? <Spinner className="w-4 h-4 border-2" />
                        : <Trash2 className="w-4 h-4" />}
                    </button>
                  </div>

                  {isExpanded
                    ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
                </div>

                {/* ── Content list ── */}
                {isExpanded && (
                  <div>
                    {isLoadingC ? (
                      <div className="px-5 py-4 space-y-2">
                        {[0, 1, 2].map(k => (
                          <div key={k} className="h-8 bg-slate-100 dark:bg-slate-800 rounded-lg animate-pulse" />
                        ))}
                      </div>
                    ) : contents.length === 0 ? (
                      <div className="px-5 py-6 text-center">
                        <p className="text-sm text-slate-400 dark:text-slate-500">
                          Chưa có nội dung. Nhấn&nbsp;
                          <span className="font-semibold">+</span>
                          &nbsp;để thêm.
                        </p>
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-100 dark:divide-slate-800">
                        {contents.map((c, ci) => (
                          <div
                            key={c.id}
                            className="flex items-center gap-3 px-5 py-3 group hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors"
                          >
                            {/* Index */}
                            <span className="text-slate-400 dark:text-slate-500 flex-shrink-0 w-4 text-xs text-right">
                              {ci + 1}
                            </span>

                            {/* Type icon */}
                            <span className="text-slate-400 dark:text-slate-500 flex-shrink-0">
                              {CONTENT_ICON[c.type] ?? <File className="w-3.5 h-3.5" />}
                            </span>

                            <p className="flex-1 text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                              {c.title}
                            </p>

                            <ContentTypeBadge type={c.type} />
                            {c.is_mandatory && <Badge variant="yellow">Bắt buộc</Badge>}

                            {/* AI Index */}
                            <div className="ml-2">
                              <AIIndexButton
                                contentId={c.id}
                                contentType={c.type}
                                filePath={c.metadata?.file_path || null}
                                initialStatus={c.ai_index_status || "not_indexed"}
                              />
                            </div>

                            {/* Hover actions */}
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              {(c.type === "DOCUMENT" || c.type === "VIDEO" || c.type === "IMAGE") && (
                                <button
                                  title="Tạo bài học micro từ file này"
                                  className="p-1.5 rounded-lg hover:bg-violet-50 dark:hover:bg-violet-950/30 text-violet-600 dark:text-violet-400"
                                  onClick={() => {
                                    setMicroPresetContentId(c.id);
                                    setMicroPresetSectionId(sec.id);
                                    setShowMicroModal(true);
                                  }}
                                >
                                  <Sparkles className="w-3.5 h-3.5" />
                                </button>
                              )}
                              <button
                                title="Xem nội dung"
                                className="p-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500"
                                onClick={() => { setViewingContent(c); setShowContentViewer(true); }}
                              >
                                <Eye className="w-3.5 h-3.5" />
                              </button>
                              <button
                                title="Chỉnh sửa"
                                className="p-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500"
                                onClick={() => { setEditingContent(c); setShowEditContentModal(true); }}
                              >
                                <Edit3 className="w-3.5 h-3.5" />
                              </button>
                              <button
                                title="Xóa"
                                disabled={deletingContent === c.id}
                                className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500"
                                onClick={() => deleteContent(c.id, sec.id)}
                              >
                                {deletingContent === c.id
                                  ? <Spinner className="w-3.5 h-3.5 border-2" />
                                  : <Trash2 className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Modals ────────────────────────────────────────────────────────── */}

      {showSectionModal && (
        <SectionModal
          courseId={courseId}
          section={editingSection}
          existingSections={sections}
          onClose={() => { setShowSectionModal(false); setEditingSection(null); }}
          onSuccess={() => { setShowSectionModal(false); setEditingSection(null); onSectionsChange(); }}
        />
      )}

      {showContentModal && selectedSectionId && (
        <ContentModal
          sectionId={selectedSectionId}
          existingContents={sectionContents[selectedSectionId] ?? []}
          onClose={() => { setShowContentModal(false); setSelectedSectionId(null); }}
          onSuccess={() => {
            setShowContentModal(false);
            if (selectedSectionId) reloadSectionContent(selectedSectionId);
            setSelectedSectionId(null);
          }}
        />
      )}

      {showBulkModal && selectedSectionId && (
        <BulkUploadModal
          sectionId={selectedSectionId}
          onClose={() => { setShowBulkModal(false); setSelectedSectionId(null); }}
          onSuccess={() => {
            setShowBulkModal(false);
            if (selectedSectionId) reloadSectionContent(selectedSectionId);
            setSelectedSectionId(null);
          }}
        />
      )}

      {showEditContentModal && editingContent && (
        <EditContentModal
          content={editingContent}
          onClose={() => { setShowEditContentModal(false); setEditingContent(null); }}
          onSuccess={() => {
            setShowEditContentModal(false);
            reloadSectionContent(editingContent.section_id);
            setEditingContent(null);
          }}
        />
      )}

      {showMicroModal && (
        <GenerateMicroLessonsModal
          courseId={courseId}
          sections={sections}
          presetContentId={microPresetContentId}
          presetSectionId={microPresetSectionId}
          onClose={() => setShowMicroModal(false)}
          onJobCreated={(jobId) => {
            setShowMicroModal(false);
            setActiveMicroJobId(jobId);
          }}
        />
      )}

      {showMicroHistoryModal && (
        <MicroLessonHistoryModal
          courseId={courseId}
          onClose={() => setShowMicroHistoryModal(false)}
          onSelectJob={(jobId) => {
            setShowMicroHistoryModal(false);
            setActiveMicroJobId(jobId);
          }}
        />
      )}

      {activeMicroJobId !== null && (
        <MicroLessonsDrawer
          jobId={activeMicroJobId}
          sections={sections}
          onClose={() => setActiveMicroJobId(null)}
          onPublished={(sectionId) => reloadSectionContent(sectionId)}
        />
      )}

      {showContentViewer && viewingContent && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-6 py-4 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 dark:text-slate-50">
                {viewingContent.title}
              </h3>
              <button
                onClick={() => { setShowContentViewer(false); setViewingContent(null); }}
                className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors"
              >
                ✕
              </button>
            </div>
            <div className="p-6">
              <ContentViewer content={viewingContent} userRole="TEACHER" />
            </div>
          </div>
        </div>
      )}
    </div>
    </AIIndexPollerProvider>
  );
}
