"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import {
  Sparkles, RefreshCw, ChevronDown, ChevronUp,
  CheckCircle2, XCircle, BookOpen, AlertCircle,
  Layers, Zap, Clock, Search, Filter, ArrowUpDown
} from "lucide-react";
import aiService, { GeneratedQuestion, KnowledgeNode, KnowledgeGraphEdge } from "@/services/aiService";
import { cn } from "@/lib/utils";

// ─── Lazy-loaded heavy sub-components ─────────────────────────────────────────

const AINodeManager = dynamic(
  () => import("@/components/lms/teacher/ai/AINodeManager").then(m => ({ default: m.AINodeManager })),
  { ssr: false, loading: () => <div className="py-8 text-center text-sm text-slate-400">Đang tải quản lý nodes…</div> },
);

const QuizSelectorModal = dynamic(
  () => import("@/components/lms/teacher/QuizSelectorModal").then(m => ({ default: m.QuizSelectorModal })),
  { ssr: false },
);

interface Props {
  courseId: number;
}

const BLOOM_LEVELS = [
  { id: "remember",   label: "Nhớ",       emoji: "🔵" },
  { id: "understand", label: "Hiểu",      emoji: "🟢" },
  { id: "apply",      label: "Áp dụng",   emoji: "🟡" },
  { id: "analyze",    label: "Phân tích", emoji: "🟠" },
  { id: "evaluate",   label: "Đánh giá",  emoji: "🔴" },
  { id: "create",     label: "Sáng tạo",  emoji: "🟣" },
];

const STATUS_CFG = {
  DRAFT:     { label: "Chờ duyệt", cls: "bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800" },
  APPROVED:  { label: "Đã duyệt",  cls: "bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800" },
  REJECTED:  { label: "Từ chối",   cls: "bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800" },
  PUBLISHED: { label: "Đã xuất bản", cls: "bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800" },
};

function DraftCard({
  q,
  onApproveClick,
  onReject,
}: {
  q: GeneratedQuestion;
  onApproveClick: (id: number) => void;
  onReject: (id: number) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");

  const bloomEmoji = BLOOM_LEVELS.find((b) => b.id === q.bloom_level)?.emoji ?? "⚪";
  const bloomLabel = BLOOM_LEVELS.find((b) => b.id === q.bloom_level)?.label ?? q.bloom_level;
  const statusCfg = STATUS_CFG[q.status] ?? STATUS_CFG.DRAFT;

  const handleApprove = () => {
    onApproveClick(q.id);
  };

  const handleReject = async () => {
    if (!note.trim()) { alert("Vui lòng nhập lý do từ chối."); return; }
    setRejecting(true);
    try { await onReject(q.id); } finally { setRejecting(false); }
  };

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-md transition-all">
      {/* Header row */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-lg flex-shrink-0">{bloomEmoji}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-50 truncate">{q.question_text}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-slate-500 dark:text-slate-400">{bloomLabel}</span>
            {q.node_name && (
              <>
                <span className="text-slate-300 dark:text-slate-700">·</span>
                <span className="text-xs text-slate-500 dark:text-slate-400">{q.node_name}</span>
              </>
            )}
          </div>
        </div>
        <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0", statusCfg.cls)}>
          {statusCfg.label}
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
      </div>

      {/* Expanded */}
      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-slate-100 dark:border-slate-800 pt-4">
          {/* Answer options */}
          <div className="space-y-2">
            {q.answer_options.map((opt, i) => (
              <div
                key={i}
                className={cn(
                  "flex items-start gap-2.5 px-3 py-2.5 rounded-xl text-sm border",
                  opt.is_correct
                    ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800 text-green-800 dark:text-green-300"
                    : "bg-slate-50 dark:bg-slate-800/40 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300"
                )}
              >
                <span className="flex-shrink-0 mt-0.5">{opt.is_correct ? "✓" : String.fromCharCode(65 + i) + "."}</span>
                <div className="flex-1">
                  <p>{opt.text}</p>
                  {opt.is_correct && opt.explanation && (
                    <p className="text-xs text-green-700 dark:text-green-400 mt-1 opacity-80">{opt.explanation}</p>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Explanation & source */}
          {q.explanation && (
            <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-xl p-3 text-sm text-blue-800 dark:text-blue-300">
              <p className="font-semibold text-xs uppercase tracking-wide mb-1 text-blue-600 dark:text-blue-400">Giải thích</p>
              {q.explanation}
            </div>
          )}
          {q.source_quote && (
            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-3 text-xs text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 italic">
              <p className="font-semibold not-italic mb-1 text-slate-500 dark:text-slate-400">Trích từ tài liệu:</p>
              {q.source_quote}
            </div>
          )}

          {/* Actions (only for DRAFT) */}
          {q.status === "DRAFT" && (
            <div className="flex gap-2 pt-2">
              <button
                onClick={handleApprove}
                className="flex items-center gap-1.5 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold rounded-xl transition-all active:scale-95"
              >
                <CheckCircle2 className="w-4 h-4" />
                Duyệt
              </button>
              <div className="flex-1 flex gap-2">
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Lý do từ chối…"
                  className="flex-1 px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-xl bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-400"
                />
                <button
                  onClick={handleReject}
                  disabled={rejecting}
                  className="flex items-center gap-1.5 px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-xl transition-all active:scale-95 disabled:opacity-50"
                >
                  <XCircle className="w-4 h-4" />
                  {rejecting ? "…" : "Từ chối"}
                </button>
              </div>
            </div>
          )}
          {q.review_note && (
            <p className="text-xs text-slate-500 dark:text-slate-400 italic">Ghi chú: {q.review_note}</p>
          )}
        </div>
      )}
    </div>
  );
}

export function AIQuizGenPanel({ courseId }: Props) {
  const [nodes, setNodes] = useState<KnowledgeNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<KnowledgeGraphEdge[]>([]);
  const [drafts, setDrafts] = useState<GeneratedQuestion[]>([]);
  const [selectedNode, setSelectedNode] = useState<number | null>(null);
  const [selectedBlooms, setSelectedBlooms] = useState<string[]>(["remember", "understand", "apply"]);
  const [language, setLanguage] = useState("vi");
  const [generating, setGenerating] = useState(false);
  const [loadingDrafts, setLoadingDrafts] = useState(false);
  const [error, setError] = useState("");
  const [activeSection, setActiveSection] = useState<"nodes" | "generate" | "drafts">("nodes");
  
  // Quiz selector modal states
  const [isQuizSelectorOpen, setIsQuizSelectorOpen] = useState(false);
  const [pendingQuestionId, setPendingQuestionId] = useState<number | null>(null);
  const [approvingId, setApprovingId] = useState<number | null>(null);
  
  // Filtering & Sorting states
  const [searchQuery, setSearchQuery] = useState("");
  const [filterBloom, setFilterBloom] = useState<string>("all");
  const [filterNode, setFilterNode]   = useState<string>("all");
  const [sortBy, setSortBy]           = useState<"newest" | "oldest" | "bloom" | "node">("newest");

  const loadNodes = useCallback(async () => {
    try {
      const data = await aiService.listKnowledgeNodes(courseId);
      setNodes(data);
    } catch {
      // nodes might not be configured yet
    }
  }, [courseId]);

  const loadGraph = useCallback(async () => {
    try {
      const graph = await aiService.getKnowledgeGraph(courseId);
      setGraphEdges(graph.edges ?? []);
    } catch {
      // graph endpoint may not be available
    }
  }, [courseId]);

  const loadDrafts = useCallback(async () => {
    setLoadingDrafts(true);
    try {
      const data = await aiService.listDraftQuestions(courseId);
      
      // LÀM PHẲNG DỮ LIỆU Ở ĐÂY:
      const formattedDrafts = data.map((q: any) => ({
        ...q,
        // Kiểm tra nếu là chuỗi thì ép kiểu về mảng object, nếu đã là mảng thì giữ nguyên
        answer_options: typeof q.answer_options === 'string' 
          ? JSON.parse(q.answer_options) 
          : q.answer_options
      }));
      setDrafts(formattedDrafts);
    } catch (e: any) {
      setError(e?.response?.data?.error ?? "Không tải được danh sách câu hỏi.");
    } finally {
      setLoadingDrafts(false);
    }
  }, [courseId]);

  useEffect(() => {
    loadNodes();
    loadGraph();
    loadDrafts();
  }, [loadNodes, loadGraph, loadDrafts]);

  const handleGenerateQuiz = async () => {
    if (!selectedNode) { alert("Vui lòng chọn chủ đề (Knowledge Node)."); return; }
    if (selectedBlooms.length === 0) { alert("Vui lòng chọn ít nhất 1 cấp độ Bloom."); return; }
    setGenerating(true);
    setError("");
    
    try {
      const response = await aiService.generateQuiz(courseId, selectedNode, {
        bloom_levels: selectedBlooms,
        language,
        questions_per_level: 1,
      });

      if (!response || !response.job_id) {
        throw new Error("Không nhận được Job ID từ server.");
      }

      // Polling Logic
      let isDone = false;
      while (!isDone) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        
        const statusCheck = await aiService.getJobStatus(response.job_id);
        if (statusCheck.status === "completed") {
          isDone = true;
          await new Promise((resolve) => setTimeout(resolve, 1000));
          setActiveSection("drafts");
          await loadDrafts();
          const { default: toast } = await import("react-hot-toast");
          toast.success("Tạo câu hỏi hoàn tất!");
        } else if (statusCheck.status === "failed") {
          isDone = true;
          throw new Error(statusCheck.error || "Quá trình tạo lỗi.");
        }
        // If pending or processing, loop continues
      }
      
    } catch (e: any) {
      setError(e?.response?.data?.error ?? e.message ?? "Không thể tạo quiz. Kiểm tra AI service.");
    } finally {
      setGenerating(false);
    }
  };

  const handleApproveClick = (questionId: number) => {
    setPendingQuestionId(questionId);
    setIsQuizSelectorOpen(true);
  };

  const handleQuizSelected = async (quizId: number) => {
    if (!pendingQuestionId) return;
    
    setApprovingId(pendingQuestionId);
    try {
      await aiService.approveQuestion(pendingQuestionId, quizId);
      await loadDrafts();
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Lỗi khi duyệt câu hỏi");
    } finally {
      setApprovingId(null);
      setPendingQuestionId(null);
    }
  };

  const handleRejectQuestion = async (id: number) => {
    await aiService.rejectQuestion(id, "Câu hỏi không phù hợp");
    await loadDrafts();
  };

  // Derived unique nodes for filter dropdown
  const uniqueNodes = useMemo(() => {
    const nodesInDrafts = drafts
      .map(d => d.node_name)
      .filter((name): name is string => !!name);
    return Array.from(new Set(nodesInDrafts)).sort();
  }, [drafts]);

  // Main filtering & sorting logic
  const filteredDrafts = useMemo(() => {
    let result = [...drafts];

    // 1. Filter by status (only show DRAFT in the main view)
    result = result.filter(d => d.status === "DRAFT");

    // 2. Filter by Bloom level
    if (filterBloom !== "all") {
      result = result.filter(d => d.bloom_level === filterBloom);
    }

    // 3. Filter by Knowledge Node
    if (filterNode !== "all") {
      result = result.filter(d => d.node_name === filterNode);
    }

    // 4. Search by text
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(d => 
        d.question_text.toLowerCase().includes(q) || 
        d.node_name?.toLowerCase().includes(q)
      );
    }

    // 5. Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case "oldest": return a.id - b.id;
        case "bloom": {
          const idxA = BLOOM_LEVELS.findIndex(bl => bl.id === a.bloom_level);
          const idxB = BLOOM_LEVELS.findIndex(bl => bl.id === b.bloom_level);
          return idxA - idxB;
        }
        case "node": return (a.node_name || "").localeCompare(b.node_name || "");
        case "newest":
        default:
          return b.id - a.id;
      }
    });

    return result;
  }, [drafts, filterBloom, filterNode, searchQuery, sortBy]);

  const draftCount = drafts.filter((d) => d.status === "DRAFT").length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-violet-100 dark:bg-violet-950/30 flex items-center justify-center border border-violet-200 dark:border-violet-800">
          <Sparkles className="w-5 h-5 text-violet-600 dark:text-violet-400" />
        </div>
        <div>
          <h3 className="font-bold text-slate-900 dark:text-slate-50">AI Tạo câu hỏi</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">Blooms Taxonomy · RAG-grounded · Không hallucination</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1">
        {(["nodes", "generate", "drafts"] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setActiveSection(t);
            }}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-all",
              activeSection === t
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-50 shadow-sm"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100"
            )}
          >
            {t === "nodes" && <BookOpen className="w-3.5 h-3.5" />}
            {t === "generate" && <Zap className="w-3.5 h-3.5" />}
            {t === "drafts" && <Clock className="w-3.5 h-3.5" />}
            {t === "nodes" ? "Nodes" : t === "generate" ? "Tạo mới" : `Chờ duyệt (${draftCount})`}
          </button>
        ))}
      </div>

      {error && (
        <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-xl text-sm text-red-700 dark:text-red-400">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {/* Generate tab */}
      {activeSection === "generate" && (
        <div className="space-y-5">
          {/* Node selector */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Chủ đề (Knowledge Node) *
            </label>
            {nodes.length === 0 ? (
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-xl text-sm text-amber-700 dark:text-amber-400">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                Chưa có Knowledge Node nào. Tạo node trong phần quản lý AI trước.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {nodes.map((n) => (
                  <button
                    key={n.id}
                    onClick={() => setSelectedNode(n.id)}
                    className={cn(
                      "flex items-center gap-2 p-3 rounded-xl border text-left text-sm transition-all",
                      selectedNode === n.id
                        ? "border-violet-400 dark:border-violet-600 bg-violet-50 dark:bg-violet-950/30 text-violet-800 dark:text-violet-200"
                        : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-600"
                    )}
                  >
                    <BookOpen className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="truncate">{n.name_vi ?? n.name}</span>
                    {n.chunk_count > 0 && (
                      <span className="ml-auto text-xs text-slate-400">{n.chunk_count} chunks</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Bloom levels */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Cấp độ Bloom *
            </label>
            <div className="flex flex-wrap gap-2">
              {BLOOM_LEVELS.map((b) => {
                const active = selectedBlooms.includes(b.id);
                return (
                  <button
                    key={b.id}
                    onClick={() => setSelectedBlooms((prev) =>
                      active ? prev.filter((x) => x !== b.id) : [...prev, b.id]
                    )}
                    className={cn(
                      "flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-sm font-medium transition-all",
                      active
                        ? "border-violet-400 dark:border-violet-600 bg-violet-50 dark:bg-violet-950/30 text-violet-800 dark:text-violet-200"
                        : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300"
                    )}
                  >
                    <span>{b.emoji}</span>
                    {b.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Language */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Ngôn ngữ</label>
            <div className="flex gap-2">
              {[{ v: "vi", l: "🇻🇳 Tiếng Việt" }, { v: "en", l: "🇺🇸 English" }].map((lang) => (
                <button
                  key={lang.v}
                  onClick={() => setLanguage(lang.v)}
                  className={cn(
                    "flex-1 py-2 rounded-xl border text-sm font-medium transition-all",
                    language === lang.v
                      ? "border-violet-400 dark:border-violet-600 bg-violet-50 dark:bg-violet-950/30 text-violet-800 dark:text-violet-200"
                      : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400"
                  )}
                >
                  {lang.l}
                </button>
              ))}
            </div>
          </div>

          {/* Generate button */}
          <button
            onClick={handleGenerateQuiz}
            disabled={generating || !selectedNode || selectedBlooms.length === 0}
            className="w-full flex items-center justify-center gap-2 py-3 bg-violet-600 hover:bg-violet-700 text-white font-semibold rounded-xl transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          >
            {generating ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                AI đang tạo câu hỏi…
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Tạo {selectedBlooms.length} câu hỏi với AI
              </>
            )}
          </button>

          <p className="text-xs text-slate-400 dark:text-slate-500 text-center">
            AI sẽ tạo 1 câu hỏi per cấp độ Bloom, grounded trong tài liệu thực tế của khóa học.
          </p>
        </div>
      )}

      {/* Drafts tab */}
      {activeSection === "drafts" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {filteredDrafts.length === draftCount 
                ? `${draftCount} chờ duyệt` 
                : `${filteredDrafts.length} / ${draftCount} kết quả`
              }
            </p>
            <button onClick={loadDrafts} disabled={loadingDrafts}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors disabled:opacity-40">
              <RefreshCw className={cn("w-3.5 h-3.5", loadingDrafts && "animate-spin")} />
              Làm mới
            </button>
          </div>

          {/* Filter Bar */}
          <div className="space-y-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input 
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Tìm kiếm nội dung câu hỏi..."
                className="w-full pl-8 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-1 focus:ring-violet-500/30 transition-all placeholder:text-slate-400"
              />
            </div>
            
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <div className="flex items-center gap-1 text-slate-500 bg-slate-100 dark:bg-slate-800 px-1.5 py-1 rounded-lg">
                <Filter className="w-3 h-3" />
                <span className="font-bold uppercase tracking-tighter">Bloom:</span>
                <select
                  value={filterBloom}
                  onChange={e => setFilterBloom(e.target.value)}
                  className="bg-transparent border-none focus:ring-0 cursor-pointer font-medium p-0"
                >
                  <option value="all">Tất cả</option>
                  {BLOOM_LEVELS.map(b => (
                    <option key={b.id} value={b.id}>{b.label}</option>
                  ))}
                </select>
              </div>

              {uniqueNodes.length > 0 && (
                <div className="flex items-center gap-1 text-slate-500 bg-slate-100 dark:bg-slate-800 px-1.5 py-1 rounded-lg">
                  <Filter className="w-3 h-3" />
                  <span className="font-bold uppercase tracking-tighter">Node:</span>
                  <select
                    value={filterNode}
                    onChange={e => setFilterNode(e.target.value)}
                    className="bg-transparent border-none focus:ring-0 cursor-pointer font-medium p-0 max-w-[120px]"
                  >
                    <option value="all">Tất cả</option>
                    {uniqueNodes.map(n => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="flex items-center gap-1 text-slate-500 bg-slate-100 dark:bg-slate-800 px-1.5 py-1 rounded-lg ml-auto">
                <ArrowUpDown className="w-3 h-3" />
                <span className="font-bold uppercase tracking-tighter">Xếp:</span>
                <select
                  value={sortBy}
                  onChange={e => setSortBy(e.target.value as any)}
                  className="bg-transparent border-none focus:ring-0 cursor-pointer font-medium p-0"
                >
                  <option value="newest">Mới</option>
                  <option value="oldest">Cũ</option>
                  <option value="bloom">Bloom</option>
                  <option value="node">Node</option>
                </select>
              </div>
            </div>
          </div>

          {loadingDrafts ? (
            <div className="flex items-center justify-center py-8 gap-3">
              <div className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-slate-500">Đang tải…</p>
            </div>
          ) : filteredDrafts.length === 0 ? (
            <div className="py-8 text-center bg-slate-50 dark:bg-slate-800/30 rounded-2xl border border-dashed border-slate-200 dark:border-slate-800/50">
              <Layers className="w-8 h-8 text-slate-300 dark:text-slate-700 mx-auto mb-2 opacity-50" />
              <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">
                {searchQuery || filterBloom !== "all" || filterNode !== "all" 
                  ? "Không tìm thấy câu hỏi phù hợp."
                  : "Chưa có câu hỏi nào. Hãy tạo mới ở tab Tạo mới."}
              </p>
            </div>
          ) : (
            filteredDrafts.map((q) => (
              <div key={q.id} className={approvingId === q.id ? "opacity-50 pointer-events-none" : ""}>
                <DraftCard
                  q={q}
                  onApproveClick={handleApproveClick}
                  onReject={handleRejectQuestion}
                />
                {approvingId === q.id && (
                  <div className="flex items-center justify-center gap-2 py-2 text-sm text-violet-600 dark:text-violet-400">
                    <div className="w-3 h-3 border-2 border-violet-600 border-t-transparent rounded-full animate-spin dark:border-violet-400" />
                    Đang duyệt…
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {activeSection === "nodes" && (
        <AINodeManager
          courseId={courseId}
          nodes={nodes}
          graphEdges={graphEdges}
          onNodesChange={() => { loadNodes(); loadGraph(); }}
        />
      )}

      {/* Quiz Selector Modal */}
      <QuizSelectorModal
        courseId={courseId}
        isOpen={isQuizSelectorOpen}
        onClose={() => setIsQuizSelectorOpen(false)}
        onSelect={handleQuizSelected}
      />
    </div>
  );
}
