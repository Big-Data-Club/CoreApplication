"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Sparkles,
  ArrowRight,
  Loader2,
  AlertCircle,
  CheckCircle2,
  X,
} from "lucide-react";
import toast from "react-hot-toast";
import aiService, {
  ConsolidationGroup,
  ConsolidationPreview,
} from "@/services/aiService";
import { cn } from "@/lib/utils";

interface Props {
  courseId: number;
  open: boolean;
  onClose: () => void;
  onCompleted: () => void;
}

type Phase = "loading" | "preview" | "executing" | "done" | "error";

const KIND_BADGE: Record<string, { label: string; cls: string }> = {
  hard:  { label: "Trùng lặp",  cls: "bg-rose-50 text-rose-700 border-rose-200" },
  soft:  { label: "Tương đồng", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  micro: { label: "Mảnh nhỏ",   cls: "bg-sky-50 text-sky-700 border-sky-200" },
};

export default function GraphConsolidateModal({ courseId, open, onClose, onCompleted }: Props) {
  const [phase, setPhase]       = useState<Phase>("loading");
  const [preview, setPreview]   = useState<ConsolidationPreview | null>(null);
  const [error, setError]       = useState<string>("");
  const [enabled, setEnabled]   = useState<Record<number, boolean>>({});
  const [statusMsg, setStatusMsg] = useState<string>("");

  // Reset & fetch the dry-run plan whenever the modal opens.
  useEffect(() => {
    if (!open) return;
    setPhase("loading");
    setError("");
    setPreview(null);
    setStatusMsg("");

    aiService
      .previewGraphConsolidation(courseId)
      .then((p) => {
        setPreview(p);
        setEnabled(Object.fromEntries(p.groups.map((g) => [g.survivor_id, true])));
        setPhase("preview");
      })
      .catch((e: any) => {
        setError(e?.response?.data?.error ?? e?.message ?? "Không thể tải kế hoạch hợp nhất");
        setPhase("error");
      });
  }, [open, courseId]);

  const stats = useMemo(() => {
    if (!preview) return { selectedGroups: 0, willAbsorb: 0 };
    let willAbsorb = 0;
    let selectedGroups = 0;
    for (const g of preview.groups) {
      if (enabled[g.survivor_id]) {
        selectedGroups += 1;
        willAbsorb += g.absorbed_ids.length;
      }
    }
    return { selectedGroups, willAbsorb };
  }, [preview, enabled]);

  const handleToggle = (survivorId: number) => {
    setEnabled((m) => ({ ...m, [survivorId]: !m[survivorId] }));
  };

  const handleConfirm = async () => {
    if (!preview || stats.selectedGroups === 0) return;

    setPhase("executing");
    setStatusMsg("Đang gửi yêu cầu…");
    try {
      const job = await aiService.triggerGraphConsolidation(courseId);
      setStatusMsg("Đang xử lý ở backend…");

      // Poll the existing AI job-status endpoint.
      const start = Date.now();
      const TIMEOUT_MS = 5 * 60 * 1000;
      while (Date.now() - start < TIMEOUT_MS) {
        await new Promise((r) => setTimeout(r, 2500));
        try {
          const s = await aiService.getJobStatus(job.job_id);
          if (s.status === "completed") {
            setPhase("done");
            toast.success("Đã làm gọn graph");
            onCompleted();
            return;
          }
          if (s.status === "failed") {
            setError(s.error || "Backend báo lỗi khi hợp nhất");
            setPhase("error");
            return;
          }
        } catch {
          // Status not seeded yet; keep polling.
        }
      }

      // Soft timeout — the job may still finish later, but stop blocking the UI.
      setPhase("done");
      toast("Hợp nhất đang chạy nền — graph sẽ tự cập nhật.", { icon: "ℹ️" });
      onCompleted();
    } catch (e: any) {
      setError(e?.response?.data?.error ?? e?.message ?? "Không thể chạy hợp nhất");
      setPhase("error");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-slate-900 w-full max-w-3xl max-h-[90vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-slate-200 dark:border-slate-700">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-violet-50 to-fuchsia-50 dark:from-violet-950/40 dark:to-fuchsia-950/40">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-violet-600" />
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Làm gọn Graph
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-white/60 dark:hover:bg-slate-800 text-slate-500"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {phase === "loading" && (
            <div className="flex flex-col items-center justify-center py-12 text-slate-500">
              <Loader2 className="w-8 h-8 animate-spin mb-3 text-violet-500" />
              <p className="text-sm">Đang phân tích graph…</p>
            </div>
          )}

          {phase === "error" && (
            <div className="flex items-start gap-3 p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-xl">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-red-700 dark:text-red-300">
                {error || "Đã xảy ra lỗi không xác định"}
              </div>
            </div>
          )}

          {phase === "done" && (
            <div className="flex flex-col items-center justify-center py-12 text-slate-700 dark:text-slate-200">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mb-3" />
              <p className="text-sm font-medium">Đã hoàn tất hợp nhất</p>
              {preview && (
                <p className="text-xs text-slate-500 mt-1">
                  Graph từ {preview.total_nodes_before} → {preview.total_nodes_after} nodes
                </p>
              )}
            </div>
          )}

          {phase === "executing" && (
            <div className="flex flex-col items-center justify-center py-12 text-slate-500">
              <Loader2 className="w-8 h-8 animate-spin mb-3 text-violet-500" />
              <p className="text-sm">{statusMsg || "Đang xử lý…"}</p>
            </div>
          )}

          {phase === "preview" && preview && (
            <>
              {/* Summary */}
              <div className="mb-4 p-3 rounded-xl bg-violet-50 dark:bg-violet-950/30 border border-violet-200 dark:border-violet-800 text-sm text-violet-700 dark:text-violet-300">
                {preview.groups.length === 0 ? (
                  <span>
                    Graph đã sạch — không có nhóm nào cần hợp nhất.
                  </span>
                ) : (
                  <span>
                    Sẽ hợp nhất{" "}
                    <strong>{stats.willAbsorb + stats.selectedGroups}</strong> nodes
                    thành <strong>{stats.selectedGroups}</strong> nhóm — graph còn{" "}
                    <strong>{preview.total_nodes_before - stats.willAbsorb}</strong>/{
                      preview.total_nodes_before
                    }{" "}
                    nodes (giảm{" "}
                    {Math.round(
                      (100 * stats.willAbsorb) /
                        Math.max(1, preview.total_nodes_before)
                    )}
                    %).
                  </span>
                )}
              </div>

              {/* Group list */}
              <div className="space-y-3">
                {preview.groups.map((g) => (
                  <GroupCard
                    key={g.survivor_id}
                    group={g}
                    enabled={!!enabled[g.survivor_id]}
                    onToggle={() => handleToggle(g.survivor_id)}
                  />
                ))}
              </div>

              {preview.groups.length === 0 && (
                <p className="text-sm text-slate-500 text-center py-8">
                  Không phát hiện node nào trùng lặp ở thời điểm này.
                </p>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={phase === "executing"}
            className="px-4 py-2 text-sm border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition disabled:opacity-50"
          >
            {phase === "done" ? "Đóng" : "Hủy"}
          </button>
          {phase === "preview" && preview && preview.groups.length > 0 && (
            <button
              onClick={handleConfirm}
              disabled={stats.selectedGroups === 0}
              className="px-4 py-2 text-sm font-semibold bg-violet-600 hover:bg-violet-700 text-white rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Xác nhận Làm gọn
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function GroupCard({
  group,
  enabled,
  onToggle,
}: {
  group: ConsolidationGroup;
  enabled: boolean;
  onToggle: () => void;
}) {
  const survivorName = group.old_names[String(group.survivor_id)] ?? group.new_name_vi ?? group.new_name;
  const badge = KIND_BADGE[group.kind] ?? KIND_BADGE.soft;

  return (
    <div
      className={cn(
        "rounded-xl border p-4 transition-all",
        enabled
          ? "border-violet-300 dark:border-violet-700 bg-white dark:bg-slate-900"
          : "border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 opacity-60"
      )}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={enabled}
          onChange={onToggle}
          className="mt-1 w-4 h-4 accent-violet-600"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={cn(
                "text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full border",
                badge.cls
              )}
            >
              {badge.label}
            </span>
            <span className="text-xs text-slate-500">
              độ tương đồng {Math.round(group.similarity * 100)}%
            </span>
          </div>

          {/* Merge visualization */}
          <div className="mt-2 flex items-center gap-2 flex-wrap text-sm">
            {group.absorbed_ids.map((aid) => (
              <span
                key={aid}
                className="px-2 py-1 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 line-through decoration-rose-400"
                title={`#${aid}`}
              >
                {group.old_names[String(aid)] ?? `#${aid}`}
              </span>
            ))}
            <ArrowRight className="w-4 h-4 text-slate-400" />
            <span className="px-2 py-1 rounded-md bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-200 font-semibold">
              {group.new_name_vi || group.new_name || survivorName}
            </span>
          </div>

          {group.new_description && (
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-400 line-clamp-2">
              {group.new_description}
            </p>
          )}

          {group.reason && (
            <p className="mt-1.5 text-[11px] italic text-slate-500">
              {group.reason}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
