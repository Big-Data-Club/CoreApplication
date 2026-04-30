"use client";

import React, { useState } from "react";
import { useAIIndexStatus } from "@/hooks/useAIIndexPoller";

type IndexStatus = "not_indexed" | "unindexed" | "pending" | "processing" | "indexed" | "failed";

interface AIIndexButtonProps {
  contentId: number;
  contentType: string;
  filePath: string | null;
  initialStatus?: IndexStatus;
  onIndexed?: (contentId: number) => void;
}

const INDEXABLE_TYPES = new Set(["TEXT", "DOCUMENT", "VIDEO", "IMAGE"]);

export function AIIndexButton({
  contentId,
  contentType,
  initialStatus = "not_indexed",
}: AIIndexButtonProps) {
  const { status, info, triggerIndex } = useAIIndexStatus(contentId, initialStatus);
  const [loading, setLoading] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const isIndexable = INDEXABLE_TYPES.has(contentType);

  if (!isIndexable) return null;

  // ── Trigger index ───────────────────────────────────────────────────────────
  const handleIndex = async () => {
    if (loading || status === "processing") return;

    const confirm =
      status === "indexed"
        ? window.confirm(
            "Tài liệu đã được index. Re-index sẽ xóa các knowledge nodes cũ và tạo lại. Tiếp tục?"
          )
        : true;

    if (!confirm) return;

    setLoading(true);
    try {
      await triggerIndex();
    } catch {
      // Status will be updated by the poller
    } finally {
      setLoading(false);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  const statusConfig: Record<
    IndexStatus,
    { icon: React.ReactNode; label: string; color: string; bg: string; border: string }
  > = {
    not_indexed: {
      icon: <BrainIcon />,
      label: "Chưa index",
      color: "text-slate-500 dark:text-slate-400",
      bg: "hover:bg-slate-100 dark:hover:bg-slate-800",
      border: "border-slate-300 dark:border-slate-600",
    },
    unindexed: {
      icon: <BrainIcon />,
      label: "Chưa index",
      color: "text-slate-500 dark:text-slate-400",
      bg: "hover:bg-slate-100 dark:hover:bg-slate-800",
      border: "border-slate-300 dark:border-slate-600",
    },
    pending: {
      icon: <BrainIcon />,
      label: "Chờ index",
      color: "text-yellow-500 dark:text-yellow-400",
      bg: "hover:bg-yellow-100 dark:hover:bg-yellow-800",
      border: "border-yellow-300 dark:border-yellow-600",
    },
    processing: {
      icon: <SpinnerIcon />,
      label: "Đang phân tích...",
      color: "text-blue-600 dark:text-blue-400",
      bg: "bg-blue-50 dark:bg-blue-950/30",
      border: "border-blue-300 dark:border-blue-700",
    },
    indexed: {
      icon: <CheckIcon />,
      label: `${info.nodes_created} nodes · ${info.chunks_created} chunks`,
      color: "text-emerald-600 dark:text-emerald-400",
      bg: "hover:bg-emerald-50 dark:hover:bg-emerald-950/30",
      border: "border-emerald-300 dark:border-emerald-700",
    },
    failed: {
      icon: <ErrorIcon />,
      label: "Lỗi — thử lại",
      color: "text-red-500 dark:text-red-400",
      bg: "hover:bg-red-50 dark:hover:bg-red-950/30",
      border: "border-red-300 dark:border-red-600",
    },
  };

  const normalizedStatus = (status === "unindexed" || status === "pending") ? "not_indexed" : status;
  const cfg = statusConfig[normalizedStatus as keyof typeof statusConfig] || statusConfig["not_indexed"];
  const isClickable = status !== "processing";

  return (
    <div className="relative inline-flex" onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)}>
      <button
        onClick={handleIndex}
        disabled={!isClickable}
        className={[
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium transition-all duration-200",
          cfg.color, cfg.bg, cfg.border,
          isClickable ? "cursor-pointer active:scale-95" : "cursor-default",
        ].join(" ")}
        aria-label={`AI Index: ${cfg.label}`}
      >
        <span className="w-3.5 h-3.5 flex-shrink-0">{cfg.icon}</span>
        <span className="hidden sm:inline">{cfg.label}</span>
      </button>

      {/* Tooltip */}
      {showTooltip && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 pointer-events-none">
          <div className="bg-slate-900 dark:bg-slate-700 text-white text-xs rounded-lg px-3 py-2 whitespace-nowrap shadow-lg">
            {(status === "not_indexed" || status === "unindexed" || status === "pending") && "Tự động tạo knowledge nodes từ tài liệu này"}
            {status === "processing" && "AI đang phân tích và tạo knowledge nodes..."}
            {status === "indexed" && `Đã index: ${info.nodes_created} nodes, ${info.chunks_created} chunks. Click để re-index.`}
            {status === "failed" && "Xảy ra lỗi trong quá trình index. Click để thử lại."}
          </div>
          <div className="w-2 h-2 bg-slate-900 dark:bg-slate-700 rotate-45 mx-auto -mt-1" />
        </div>
      )}
    </div>
  );
}

// ── Micro icons ────────────────────────────────────────────────────────────────

function BrainIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" stroke="currentColor" strokeWidth="1.4">
      <path d="M8 2C6.3 2 5 3.1 5 4.5c0 .4.1.7.3 1A2.5 2.5 0 003 8c0 1 .5 1.9 1.3 2.4A2 2 0 005.5 14H11a2 2 0 00.8-3.8A2.5 2.5 0 0013 8a2.5 2.5 0 00-2.3-2.5c.2-.3.3-.6.3-1C11 3.1 9.7 2 8 2z"/>
      <line x1="8" y1="6" x2="8" y2="11"/>
      <line x1="5.5" y1="8.5" x2="10.5" y2="8.5"/>
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5 animate-spin" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="5.5" strokeOpacity="0.25"/>
      <path d="M8 2.5A5.5 5.5 0 0113.5 8" strokeLinecap="round"/>
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" stroke="currentColor" strokeWidth="1.8">
      <circle cx="8" cy="8" r="6" strokeOpacity="0.4"/>
      <path d="M5 8.5l2 2 4-4" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="6"/>
      <line x1="8" y1="5" x2="8" y2="9" strokeLinecap="round"/>
      <circle cx="8" cy="11.5" r="0.75" fill="currentColor" stroke="none"/>
    </svg>
  );
}