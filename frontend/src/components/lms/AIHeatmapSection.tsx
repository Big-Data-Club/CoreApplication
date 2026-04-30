"use client";

/**
 * AIHeatmapSection.tsx
 * Knowledge-gap heatmap powered by AI.
 * Works for both student (my-heatmap) and teacher (class heatmap) views.
 *
 * Usage:
 *   <AIHeatmapSection courseId={123} role="student" />
 *   <AIHeatmapSection courseId={123} role="teacher" />
 */

import { useEffect, useState } from "react";
import { RefreshCw, Sparkles, AlertCircle, Users, TrendingDown } from "lucide-react";
import aiService, { HeatmapNode } from "@/services/aiService";
import { cn } from "@/lib/utils";

interface Props {
  courseId: number;
  role: "student" | "teacher";
}

function getMasteryColor(rate: number): string {
  // rate = wrong_rate (0-100), lower = better
  if (rate <= 10) return "bg-emerald-400 dark:bg-emerald-500";
  if (rate <= 25) return "bg-green-300 dark:bg-green-400";
  if (rate <= 40) return "bg-yellow-300 dark:bg-yellow-400";
  if (rate <= 60) return "bg-orange-400 dark:bg-orange-500";
  return "bg-red-500 dark:bg-red-600";
}

function getMasteryLabel(rate: number): string {
  if (rate <= 10) return "Rất tốt";
  if (rate <= 25) return "Tốt";
  if (rate <= 40) return "Trung bình";
  if (rate <= 60) return "Yếu";
  return "Cần cải thiện";
}

function getMasteryTextColor(rate: number): string {
  if (rate <= 10) return "text-emerald-700 dark:text-emerald-300";
  if (rate <= 25) return "text-green-700 dark:text-green-300";
  if (rate <= 40) return "text-yellow-700 dark:text-yellow-300";
  if (rate <= 60) return "text-orange-700 dark:text-orange-300";
  return "text-red-700 dark:text-red-300";
}

const formatPercent = (val: number | null | undefined) => {
  if (val == null || isNaN(val) || !isFinite(val)) return 0;
  return Number(Number(val).toFixed(2));
};

function HeatCell({ node }: { node: HeatmapNode }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className={cn(
        "rounded-xl p-3 cursor-default transition-all duration-200",
        getMasteryColor(node.wrong_rate),
        hovered && "scale-105 shadow-lg z-10"
      )}>
        <p className="text-white font-semibold text-xs leading-tight truncate">
          {node.name_vi ?? node.node_name}
        </p>
        <p className="text-white/80 text-xs mt-1 font-mono">
          {node.total_attempts === 0 ? "Chưa có TT" : `${formatPercent(node.wrong_rate)}% sai`}
        </p>
      </div>

      {/* Tooltip */}
      {hovered && (
        <div className="absolute z-20 bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 bg-slate-900 dark:bg-slate-800 text-white text-xs rounded-xl p-3 shadow-xl border border-slate-700 pointer-events-none">
          <p className="font-semibold mb-1">{node.name_vi ?? node.node_name}</p>
          <div className="space-y-0.5 text-slate-300">
            <p>{node.total_wrong}/{node.total_attempts} câu sai</p>
            {node.student_count > 0 && <p className="flex items-center gap-1"><Users className="w-3 h-3" />{node.student_count} học viên</p>}
            <p className={cn("font-medium", getMasteryTextColor(node.wrong_rate))}>
              {getMasteryLabel(node.wrong_rate)}
            </p>
          </div>
          {/* Arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-slate-800" />
        </div>
      )}
    </div>
  );
}

export function AIHeatmapSection({ courseId, role }: Props) {
  const [nodes, setNodes] = useState<HeatmapNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const fetch = async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const data = role === "teacher"
        ? await aiService.getClassHeatmap(courseId)
        : await aiService.getStudentHeatmap(courseId);
      setNodes(data);
    } catch (e: any) {
      setError(e?.response?.data?.error ?? "Không thể tải heatmap. AI service có thể chưa khởi động.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { fetch(); }, [courseId, role]);

  const weakest = [...nodes].sort((a, b) => b.wrong_rate - a.wrong_rate).slice(0, 3);

  return (
    <section className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-violet-100 dark:bg-violet-950/30 flex items-center justify-center border border-violet-200 dark:border-violet-800">
            <Sparkles className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-50">
              {role === "teacher" ? "Bản đồ điểm yếu lớp học" : "Điểm yếu của tôi"}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {role === "teacher"
                ? "Tỉ lệ sai theo chủ đề — màu đỏ = cần chú ý nhất"
                : "AI phân tích lỗi sai của bạn theo từng chủ đề"}
            </p>
          </div>
        </div>
        <button
          onClick={() => fetch(true)}
          disabled={refreshing}
          className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all disabled:opacity-40"
        >
          <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-3 py-8 justify-center">
          <div className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-500">AI đang tính toán…</p>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-3 p-4 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">AI service chưa sẵn sàng</p>
            <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {!loading && !error && nodes.length === 0 && (
        <div className="py-8 text-center">
          <Sparkles className="w-8 h-8 text-slate-300 dark:text-slate-700 mx-auto mb-2" />
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Chưa có đủ dữ liệu. Hãy làm thêm quiz để AI phân tích!
          </p>
        </div>
      )}

      {!loading && !error && nodes.length > 0 && (
        <>
          {/* Heatmap grid */}
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
            {[...nodes].sort((a, b) => {
              if (a.total_attempts === 0 && b.total_attempts === 0) return 0;
              if (a.total_attempts === 0) return 1;
              if (b.total_attempts === 0) return -1;
              return b.wrong_rate - a.wrong_rate;
            }).map((n) => <HeatCell key={n.node_id} node={n} />)}
          </div>

          {/* Legend */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs text-slate-500 dark:text-slate-400">Mức độ:</span>
            {[
              { color: "bg-emerald-400", label: "Rất tốt" },
              { color: "bg-yellow-300", label: "TB" },
              { color: "bg-orange-400", label: "Yếu" },
              { color: "bg-red-500", label: "Cần cải thiện" },
            ].map((l) => (
              <span key={l.label} className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
                <span className={cn("w-3 h-3 rounded-sm", l.color)} />
                {l.label}
              </span>
            ))}
          </div>

          {/* Top weak spots */}
          {weakest.some((n) => n.wrong_rate > 30) && (
            <div className="bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <TrendingDown className="w-4 h-4 text-rose-500" />
                <p className="text-xs font-semibold text-rose-700 dark:text-rose-400 uppercase tracking-wide">
                  Cần ôn tập ngay
                </p>
              </div>
              <div className="space-y-2">
                {weakest.filter((n) => n.wrong_rate > 30).map((n) => (
                  <div key={n.node_id} className="flex items-center justify-between">
                    <span className="text-sm text-rose-800 dark:text-rose-300 font-medium">
                      {n.name_vi ?? n.node_name}
                    </span>
                    <span className="text-xs font-bold text-rose-700 dark:text-rose-400">
                      {n.total_attempts === 0 ? "Chưa kiểm tra" : `${formatPercent(n.wrong_rate)}% sai`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
