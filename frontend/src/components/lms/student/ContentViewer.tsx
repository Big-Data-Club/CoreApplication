/* eslint-disable @next/next/no-img-element */
"use client";

/**
 * ContentViewer.tsx — Rewritten for clarity & extensibility
 *
 * Props:
 *  - content        : the content item to render
 *  - userRole       : 'STUDENT' | 'TEACHER' | 'ADMIN'
 *  - isCompleted    : whether this content item is already marked complete
 *  - onComplete     : callback fired when completion is confirmed
 *                     (Quiz: after successful submit; others: on button click / auto-timer)
 *
 * Heavy sub-components (MarkdownRenderer, QuickActionPanel) are lazy-loaded
 * to keep the initial chunk small.
 */

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import type { MicroLessonContext } from "@/components/lms/student/micro/types";

import quizService from "@/services/quizService";
import aiService from "@/services/aiService";
import { cn } from "@/lib/utils";
import { useSetPageContext } from "@/hooks/usePageContext";

// ─── Lazy-loaded heavy renderers ──────────────────────────────────────────────

const MarkdownRenderer = dynamic(
  () => import("@/components/markdown/MarkdownRenderer"),
  { ssr: false, loading: () => <div className="h-32 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse" /> },
);

const QuickActionPanel = dynamic(
  () => import("@/components/lms/student/micro/QuickActionPanel").then(m => ({ default: m.QuickActionPanel })),
  { ssr: false },
);

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ContentItem {
  id: number;
  type: "TEXT" | "VIDEO" | "IMAGE" | "DOCUMENT" | "QUIZ" | "FORUM" | "ANNOUNCEMENT" | string;
  title: string;
  description?: string;
  metadata?: Record<string, any>;
  file_path?: string | null;
  file_type?: string;
  is_mandatory?: boolean;
}

interface ContentViewerProps {
  content: ContentItem;
  userRole?: "STUDENT" | "TEACHER" | "ADMIN" | string;
  courseId?: string,
  isCompleted?: boolean;
  onComplete?: () => void;
}

// ─── Shared helpers ───────────────────────────────────────────────────────────

function buildFileUrl(filePath?: string | null): string {
  if (!filePath) return "";
  if (filePath.startsWith("http://") || filePath.startsWith("https://")) return filePath;
  return `/lmsapiv1/files/serve/${filePath}`;
}

function formatFileSize(bytes: number): string {
  if (!bytes) return "Không rõ";
  const units = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function extractYouTubeId(url: string): string {
  const match = url.match(
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/
  );
  return match?.[1] ?? "";
}

function extractVimeoId(url: string): string {
  return url.match(/vimeo\.com\/(\d+)/)?.[1] ?? "";
}

// ─── CompletionBadge ─────────────────────────────────────────────────────────

function CompletionBadge({ isCompleted }: { isCompleted: boolean }) {
  if (!isCompleted) return null;
  return (
    <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50 px-2.5 py-1 rounded-full">
      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
      Đã hoàn thành
    </div>
  );
}

// ─── TextRenderer ─────────────────────────────────────────────────────────────

function TextRenderer({
  content,
  courseId,
  userRole,
}: {
  content: ContentItem;
  courseId?: number;
  userRole?: string;
}) {
  const { patchPageContext } = useSetPageContext();

  const markdownBody = content.metadata?.content || "";
  const showPanel = userRole === "STUDENT" && !!courseId && !!markdownBody;

  // Sync lesson text to global PageContext for the Chat Sidebar
  useEffect(() => {
    if (showPanel) {
      patchPageContext({ contentBody: markdownBody });
    }
  }, [showPanel, markdownBody, patchPageContext]);

  const [nodeId, setNodeId] = useState<number | null>(null);

  // Auto-lookup knowledge nodeId linked to this content.
  // Strategy: 1) source_content_id exact match, 2) metadata.node_id,
  // 3) title match (micro-lesson TEXT has same title as its node).
  useEffect(() => {
    if (!courseId || userRole !== "STUDENT") return;

    // If content metadata already has node_id (set by micro-lesson generator)
    const metaNodeId = content.metadata?.node_id;
    if (metaNodeId) {
      setNodeId(Number(metaNodeId));
      return;
    }

    let cancelled = false;
    aiService
      .listKnowledgeNodes(courseId)
      .then((nodes) => {
        if (cancelled) return;
        // 1) Exact source_content_id match
        let match = nodes.find((n) => n.source_content_id === content.id);
        // 2) Fallback: match by title (micro-lesson TEXT shares name with its node)
        if (!match) {
          const titleLower = content.title.trim().toLowerCase();
          match = nodes.find((n) => n.name.trim().toLowerCase() === titleLower);
        }
        if (match) setNodeId(match.id);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [courseId, content.id, content.title, content.metadata, userRole]);

  return (
    <>
      <MarkdownRenderer content={markdownBody} />
      {showPanel && (
        <QuickActionPanel
          ctx={{
            lessonId: null,
            lessonTitle: content.title,
            lessonText: markdownBody,
            courseId: courseId!,
            nodeId,
            contentId: content.id,
          }}
        />
      )}
    </>
  );
}

// ─── VideoRenderer ────────────────────────────────────────────────────────────

function VideoRenderer({ content }: { content: ContentItem }) {
  const videoUrl = content.metadata?.video_url || content.metadata?.url || "";

  if (!videoUrl) {
    return (
      <EmptyState message="Video chưa được cấu hình." />
    );
  }

  const youtubeId = extractYouTubeId(videoUrl);
  if (youtubeId) {
    return (
      <div className="relative pb-[56.25%] h-0 overflow-hidden rounded-2xl shadow-sm bg-black">
        <iframe
          className="absolute inset-0 w-full h-full"
          src={`https://www.youtube.com/embed/${youtubeId}`}
          title={content.title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    );
  }

  const vimeoId = extractVimeoId(videoUrl);
  if (vimeoId) {
    return (
      <div className="relative pb-[56.25%] h-0 overflow-hidden rounded-2xl shadow-sm bg-black">
        <iframe
          className="absolute inset-0 w-full h-full"
          src={`https://player.vimeo.com/video/${vimeoId}`}
          title={content.title}
          allow="autoplay; fullscreen; picture-in-picture"
          allowFullScreen
        />
      </div>
    );
  }

  // Native video file
  const filePath = content.metadata?.file_path || content.file_path;
  const fileUrl = buildFileUrl(filePath);
  if (fileUrl) {
    return (
      <div className="space-y-3">
        <video
          controls
          className="w-full rounded-2xl shadow-sm bg-black"
          src={fileUrl}
        >
          Trình duyệt của bạn không hỗ trợ video.
        </video>
        <DownloadLink href={fileUrl.replace("/serve/", "/download/")} label="Tải xuống video" />
      </div>
    );
  }

  return <EmptyState message="Định dạng video không được hỗ trợ." />;
}

// ─── ImageRenderer ────────────────────────────────────────────────────────────

function ImageRenderer({ content }: { content: ContentItem }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  const filePath = content.metadata?.file_path || content.file_path;
  const imageUrl = filePath ? buildFileUrl(filePath) : (content.metadata?.image_url ?? "");

  if (!imageUrl) return <EmptyState message="Hình ảnh chưa được tải lên." />;

  return (
    <div className="space-y-3">
      <div className="relative bg-slate-100 dark:bg-slate-800 rounded-2xl overflow-hidden shadow-sm min-h-[200px]">
        {!loaded && !error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {error ? (
          <div className="flex items-center justify-center h-40">
            <p className="text-slate-500 text-sm">Không thể tải hình ảnh.</p>
          </div>
        ) : (
          <img
            src={imageUrl}
            alt={content.title}
            className={cn("w-full h-auto transition-opacity duration-300", loaded ? "opacity-100" : "opacity-0")}
            onLoad={() => setLoaded(true)}
            onError={() => { setError(true); setLoaded(true); }}
          />
        )}
      </div>
      <div className="flex gap-2">
        <a
          href={imageUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-xl shadow-sm transition-all active:scale-95"
        >
          Xem kích thước gốc
        </a>
        <DownloadLink href={imageUrl.replace("/serve/", "/download/")} label="Tải xuống" secondary />
      </div>
    </div>
  );
}

// ─── DocumentRenderer ─────────────────────────────────────────────────────────

function DocumentRenderer({ content }: { content: ContentItem }) {
  const [iframeError, setIframeError] = useState(false);

  const filePath = content.metadata?.file_path || content.file_path;
  const docUrl = filePath ? buildFileUrl(filePath) : (content.metadata?.file_url ?? "");

  if (!docUrl) return <EmptyState message="Tài liệu chưa được tải lên." />;

  const isPdf = docUrl.toLowerCase().includes(".pdf");
  const isOfficeDoc = /\.(docx|pptx|xlsx|doc|ppt|xls)$/i.test(docUrl);
  const fileName = content.metadata?.file_name || content.title;
  const fileSize = content.metadata?.file_size ? formatFileSize(content.metadata.file_size) : null;
  const downloadUrl = docUrl.replace("/serve/", "/download/");

  return (
    <div className="space-y-4">
      {/* File info card */}
      <div className="flex items-center gap-4 p-4 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl">
        <div className="w-10 h-10 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/50 rounded-xl flex items-center justify-center flex-shrink-0 text-lg">
          {isPdf ? "📄" : isOfficeDoc ? "📊" : "📋"}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-slate-900 dark:text-slate-50 truncate">{fileName}</p>
          {fileSize && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{fileSize}</p>}
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <a
            href={docUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm transition-all active:scale-95"
          >
            Xem
          </a>
          <DownloadLink href={downloadUrl} label="Tải xuống" secondary compact />
        </div>
      </div>

      {/* PDF embed */}
      {isPdf && !iframeError && (
        <div className="border border-slate-200 dark:border-slate-700 rounded-2xl overflow-hidden bg-slate-100 dark:bg-slate-800">
          <iframe
            src={`${docUrl}#view=FitH`}
            className="w-full h-[600px]"
            title={fileName}
            onError={() => setIframeError(true)}
          />
        </div>
      )}

      {/* Office Document Embed */}
      {isOfficeDoc && !iframeError && (
        <div className="border border-slate-200 dark:border-slate-700 rounded-2xl overflow-hidden bg-slate-100 dark:bg-slate-800">
          <iframe
            src={`https://view.officeapps.live.com/op/view.aspx?src=${encodeURIComponent(docUrl)}`}
            className="w-full h-[600px]"
            title={fileName}
            frameBorder="0"
          />
          <div className="p-3 bg-slate-50 dark:bg-slate-900/50 border-t border-slate-200 dark:border-slate-700 text-[10px] text-slate-400 text-center">
            Bản xem trước được cung cấp bởi Microsoft Office Online. Nếu không hiển thị, vui lòng tải xuống để xem.
          </div>
        </div>
      )}

      {(isPdf || isOfficeDoc) && iframeError && (
        <div className="p-4 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/50 rounded-xl text-sm text-amber-700 dark:text-amber-400">
          Không thể hiển thị tài liệu trực tiếp. Vui lòng tải xuống để xem.
        </div>
      )}
    </div>
  );
}

// ─── QuizRenderer ─────────────────────────────────────────────────────────────

interface QuizData {
  id: number;
  title: string;
  total_points?: number;
  time_limit_minutes?: number;
  max_attempts?: number;
  passing_score?: number;
  available_from?: string;
  available_until?: string;
}

function QuizRenderer({
  content,
  userRole,
  courseId,
  isCompleted,
  onComplete,
}: {
  content: ContentItem;
  userRole: string;
  courseId?: string;
  isCompleted: boolean;
  onComplete?: () => void;
}) {
  const router = useRouter();
  const [quiz, setQuiz] = useState<QuizData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasInProgress, setHasInProgress] = useState(false);

  const isTeacher = userRole === "TEACHER" || userRole === "ADMIN";
  const isStudent = userRole === "STUDENT";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    quizService.getQuizByContentId(content.id)
      .then(res => {
        if (cancelled) return;
        const q: QuizData = res?.data;
        setQuiz(q);

        if (q?.id && isStudent) {
          quizService.getMyQuizAttempts(q.id)
            .then(attRes => {
              if (cancelled) return;
              const inProg = (attRes?.data ?? []).some((a: any) => a.status === "IN_PROGRESS");
              setHasInProgress(inProg);
            })
            .catch(() => {});
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err?.response?.status === 404
            ? "Quiz chưa được tạo cho nội dung này."
            : "Không thể tải thông tin quiz.");
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [content.id, isStudent]);

  // ── Availability check ──
  const availability = (() => {
    if (!quiz) return null;
    const now = Date.now();
    if (quiz.available_from && now < new Date(quiz.available_from).getTime()) {
      return { ok: false, msg: `Quiz mở vào ${new Date(quiz.available_from).toLocaleString("vi-VN")}`, type: "upcoming" as const };
    }
    if (quiz.available_until && now > new Date(quiz.available_until).getTime()) {
      return { ok: false, msg: `Quiz đã đóng vào ${new Date(quiz.available_until).toLocaleString("vi-VN")}`, type: "expired" as const };
    }
    return { ok: true, type: "available" as const };
  })();

  const handleStart = () => {
    if (!quiz?.id) return;
    if (!availability?.ok) { alert(availability?.msg); return; }
    router.push(`/lms/student/courses/${courseId}/quiz/${quiz.id}/take?start=true`);
  };

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex items-center gap-3 p-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl">
        <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-slate-600 dark:text-slate-400 text-sm">Đang tải thông tin quiz...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Quiz info card */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 bg-violet-50 dark:bg-violet-950/30 border border-violet-200 dark:border-violet-800/50 rounded-xl flex items-center justify-center flex-shrink-0 text-lg">
            📝
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-slate-900 dark:text-slate-50 mb-1">{content.title}</p>
            {content.description && (
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">{content.description}</p>
            )}

            {/* Stats row */}
            {quiz && (
              <div className="flex flex-wrap gap-2">
                {quiz.total_points != null && (
                  <StatPill label="Tổng điểm" value={String(quiz.total_points)} />
                )}
                {quiz.time_limit_minutes != null && (
                  <StatPill label="Thời gian" value={`${quiz.time_limit_minutes} phút`} />
                )}
                {quiz.max_attempts != null && (
                  <StatPill label="Số lần làm" value={quiz.max_attempts > 0 ? `${quiz.max_attempts} lần` : "Không giới hạn"} />
                )}
                {quiz.passing_score != null && (
                  <StatPill label="Điểm đạt" value={`${quiz.passing_score}%`} />
                )}
              </div>
            )}

            {/* Date range */}
            {quiz && (quiz.available_from || quiz.available_until) && (
              <div className="flex flex-col gap-0.5 mt-3 text-xs text-slate-500 dark:text-slate-400">
                {quiz.available_from && (
                  <span>Mở từ: {new Date(quiz.available_from).toLocaleString("vi-VN")}</span>
                )}
                {quiz.available_until && (
                  <span>Đến: {new Date(quiz.available_until).toLocaleString("vi-VN")}</span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/50 rounded-xl text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Availability notice */}
      {availability && !availability.ok && (
        <div className={cn(
          "p-3 rounded-xl border text-sm font-medium",
          availability.type === "expired"
            ? "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800/50 text-red-600 dark:text-red-400"
            : "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/50 text-amber-600 dark:text-amber-400"
        )}>
          {availability.msg}
        </div>
      )}

      {/* Teacher actions */}
      {isTeacher && (
        <div className="flex gap-3">
          {quiz?.id ? (
            <>
              <ActionButton
                onClick={() => router.push(`/lms/teacher/quiz/${quiz.id}/manage`)}
                label="Quản lý Quiz"
                variant="primary"
              />
              <ActionButton
                onClick={() => router.push(`/lms/teacher/quiz/${quiz.id}/grading`)}
                label="Chấm bài"
                variant="success"
              />
            </>
          ) : (
            <ActionButton
              onClick={() => router.push(`/lms/teacher/content/${content.id}/quiz/create`)}
              label="+ Tạo Quiz"
              variant="primary"
            />
          )}
        </div>
      )}

      {/* Student actions */}
      {isStudent && quiz?.id && (
        <div className="flex gap-3">
          <button
            onClick={handleStart}
            disabled={!availability?.ok}
            className={cn(
              "flex-1 py-3.5 rounded-xl font-semibold text-sm transition-all active:scale-95 shadow-sm",
              !availability?.ok
                ? "bg-slate-200 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700 text-white"
            )}
          >
            {!availability?.ok
              ? "Không khả dụng"
              : hasInProgress
                ? "⏩ Tiếp tục làm bài"
                : "🚀 Bắt đầu làm bài"}
          </button>
          <button
            onClick={() => router.push(`/lms/student/courses/${courseId}/quiz/${quiz.id}/history`)}
            className="px-4 py-3.5 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-xl font-medium text-sm transition-all active:scale-95"
          >
            📜 Lịch sử
          </button>
        </div>
      )}

      {isStudent && !quiz?.id && !error && (
        <div className="p-4 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/50 rounded-xl text-sm text-amber-700 dark:text-amber-400 text-center">
          Quiz chưa được cấu hình. Vui lòng liên hệ giảng viên.
        </div>
      )}
    </div>
  );
}

// ─── ForumRenderer ────────────────────────────────────────────────────────────

function ForumRenderer({ content }: { content: ContentItem }) {
  const router = useRouter();
  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/50 rounded-xl flex items-center justify-center flex-shrink-0 text-lg">
          💬
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-slate-900 dark:text-slate-50 mb-1">Diễn đàn thảo luận</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
            {content.description || "Tham gia thảo luận, đặt câu hỏi và chia sẻ kiến thức."}
          </p>
          <button
            onClick={() => router.push(`/lms/forums/${content.id}`)}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold text-sm shadow-sm transition-all active:scale-95"
          >
            Vào diễn đàn →
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── AnnouncementRenderer ─────────────────────────────────────────────────────

function AnnouncementRenderer({ content }: { content: ContentItem }) {
  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">📢</span>
        <h3 className="font-semibold text-slate-900 dark:text-slate-50">Thông báo</h3>
      </div>
      {content.description && (
        <p className="text-slate-600 dark:text-slate-400 text-sm mb-4">{content.description}</p>
      )}
      {content.metadata?.content && (
        <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
          <MarkdownRenderer content={content.metadata.content} />
        </div>
      )}
    </div>
  );
}

// ─── Shared mini-components ───────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div className="p-6 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl text-center">
      <p className="text-sm text-slate-500 dark:text-slate-400">{message}</p>
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-700 dark:text-slate-300">
      <span className="text-slate-500 dark:text-slate-400">{label}:</span>
      <span className="font-semibold">{value}</span>
    </span>
  );
}

function DownloadLink({
  href, label, secondary = false, compact = false,
}: {
  href: string; label: string; secondary?: boolean; compact?: boolean;
}) {
  return (
    <a
      href={href}
      download
      className={cn(
        "inline-flex items-center gap-1.5 font-medium rounded-xl shadow-sm transition-all active:scale-95",
        compact ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-sm",
        secondary
          ? "bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
          : "bg-blue-600 hover:bg-blue-700 text-white"
      )}
    >
      📥 {label}
    </a>
  );
}

function ActionButton({
  onClick, label, variant = "primary",
}: {
  onClick: () => void; label: string; variant?: "primary" | "success";
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex-1 px-5 py-3 rounded-xl font-semibold text-sm shadow-sm transition-all active:scale-95",
        variant === "success"
          ? "bg-emerald-600 hover:bg-emerald-700 text-white"
          : "bg-blue-600 hover:bg-blue-700 text-white"
      )}
    >
      {label}
    </button>
  );
}

// ─── Main ContentViewer ───────────────────────────────────────────────────────

export default function ContentViewer({
  content,
  userRole = "STUDENT",
  courseId,
  isCompleted = false,
  onComplete,
}: ContentViewerProps) {
  const isStudent = userRole === "STUDENT";

  const renderBody = () => {
    switch (content.type) {
      case "TEXT":         return <TextRenderer         content={content} courseId={courseId ? Number(courseId) : undefined} userRole={userRole} />;
      case "VIDEO":        return <VideoRenderer        content={content} />;
      case "IMAGE":        return <ImageRenderer        content={content} />;
      case "DOCUMENT":     return <DocumentRenderer     content={content} />;
      case "FORUM":        return <ForumRenderer        content={content} />;
      case "ANNOUNCEMENT": return <AnnouncementRenderer content={content} />;
      case "QUIZ":
        return (
          <QuizRenderer
            content={content}
            userRole={userRole}
            courseId={courseId}
            isCompleted={isCompleted}
            onComplete={onComplete}
          />
        );
      default:
        return <EmptyState message={`Loại nội dung "${content.type}" chưa được hỗ trợ.`} />;
    }
  };

  return (
    <div className="space-y-4">
      {/* Completion status */}
      {isStudent && content.is_mandatory && (
        <div className="flex items-center gap-2">
          <CompletionBadge isCompleted={isCompleted} />
          {!isCompleted && content.type !== "QUIZ" && (
            <span className="text-xs text-slate-400 dark:text-slate-500">
              Xem xong nội dung này để tính vào tiến độ
            </span>
          )}
        </div>
      )}

      {/* Content body */}
      {renderBody()}

      {/* Dev debug panel */}
      {process.env.NODE_ENV === "development" && (
        <details className="text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3">
          <summary className="cursor-pointer font-mono text-slate-500">Debug</summary>
          <pre className="mt-2 overflow-auto text-slate-600 dark:text-slate-400">
            {JSON.stringify({ id: content.id, type: content.type, isCompleted, metadata: content.metadata }, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}