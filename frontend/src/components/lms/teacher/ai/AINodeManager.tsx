"use client";

import { useState, useMemo } from "react";
import dynamic from "next/dynamic";
import { Plus, ChevronDown, ChevronRight, BookOpen, AlertCircle, Network, Trash2, Sparkles } from "lucide-react";
import aiService, { KnowledgeNode, KnowledgeGraphEdge } from "@/services/aiService";
import { cn } from "@/lib/utils";
import lmsService from "@/services/lmsService";
import toast from "react-hot-toast";

// ─── Lazy-loaded heavy components ─────────────────────────────────────────────

const ContentPickerModal = dynamic(
  () => import("../ContentPickerModal").then(m => ({ default: m.ContentPickerModal })),
  { ssr: false },
);

const KnowledgeGraph = dynamic(
  () => import("../KnowledgeGraph"),
  { ssr: false, loading: () => <div className="h-[600px] bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse flex items-center justify-center text-sm text-slate-400">Đang tải Knowledge Graph…</div> },
);

const GraphConsolidateModal = dynamic(
  () => import("./GraphConsolidateModal"),
  { ssr: false },
);

interface Props {
  courseId: number;
  nodes: KnowledgeNode[];
  graphEdges: KnowledgeGraphEdge[];
  onNodesChange: () => void;
}

export function AINodeManager({ courseId, nodes, graphEdges = [], onNodesChange }: Props) {
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", name_vi: "", description: "", parent_id: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(true);
  const [viewMode, setViewMode] = useState<"list" | "graph">("graph");
  const [consolidateOpen, setConsolidateOpen] = useState(false);

  const graphData = useMemo(() => {
    const graphNodes = nodes.map(n => ({
      id: Number(n.id),
      name: n.name_vi || n.name,
      description: n.description,
      chunk_count: n.chunk_count,
    }));

    // Build a set of node IDs for validation
    const nodeIdSet = new Set(graphNodes.map(n => n.id));

    // Map edges from the knowledge graph API (already typed + directional)
    const links = graphEdges
      .filter(e => nodeIdSet.has(Number(e.source)) && nodeIdSet.has(Number(e.target)))
      .map(e => ({
        source: Number(e.source),
        target: Number(e.target),
        type: e.relation_type as string,
        strength: e.strength,
        auto_generated: e.auto_generated,
      }));

    // Add parent-child links from node.parent_id (if any)
    nodes.forEach(n => {
      if (n.parent_id && nodeIdSet.has(Number(n.parent_id))) {
        // Avoid duplicate if edge already exists from API
        const exists = links.some(
          l => l.source === Number(n.parent_id) && l.target === Number(n.id) && l.type === 'parent_child'
        );
        if (!exists) {
          links.push({
            source: Number(n.parent_id),
            target: Number(n.id),
            type: 'parent_child',
            strength: 1.0,
            auto_generated: false,
          });
        }
      }
    });

    return { nodes: graphNodes, links };
  }, [nodes, graphEdges]);

  const handleCreate = async () => {
    if (!form.name.trim()) { setError("Tên node không được để trống"); return; }
    setSaving(true);
    setError("");
    try {
      await aiService.createKnowledgeNode(courseId, {
        name: form.name.trim(),
        name_vi: form.name_vi.trim() || undefined,
        description: form.description.trim() || undefined,
        parent_id: form.parent_id ? Number(form.parent_id) : undefined,
      });
      setForm({ name: "", name_vi: "", description: "", parent_id: "" });
      setCreating(false);
      onNodesChange();
    } catch (e: any) {
      setError(e?.response?.data?.error ?? "Không thể tạo node");
    } finally {
      setSaving(false);
    }
  };

  const rootNodes = nodes.filter(n => !n.parent_id);
  const childNodes = (parentId: number) => nodes.filter(n => n.parent_id === parentId);

  const NodeRow = ({ node, depth = 0 }: { node: KnowledgeNode; depth?: number }) => {
    const children = childNodes(node.id);
    const [open, setOpen] = useState(depth === 0);
    const [showContentPicker, setShowContentPicker] = useState(false);
    const [processing, setProcessing] = useState(false);
    
    const handleLinkContent = async (contentId: number, fileUrl?: string) => {
      setProcessing(true);
      try {
        await lmsService.triggerDocumentProcessing(
          contentId,
          courseId,
          node.id,
          fileUrl
        );
        onNodesChange();
        setShowContentPicker(false);
      } catch (e: any) {
        setError(e?.response?.data?.error ?? "Lỗi khi liên kết tài liệu");
      } finally {
        setProcessing(false);
      }
    };

    const handleDeleteNode = async (e: React.MouseEvent) => {
      e.stopPropagation();
      const confirmed = window.confirm(
        `Bạn có chắc chắn muốn xóa node "${node.name_vi || node.name}"?\nHành động này sẽ xóa vĩnh viễn node khỏi cơ sở dữ liệu và các liên kết liên quan.`
      );
      if (!confirmed) return;
      
      try {
        await aiService.deleteKnowledgeNode(courseId, node.id);
        toast.success("Đã xóa node kiến thức thành công");
        onNodesChange();
      } catch (err: any) {
        toast.error(err.response?.data?.message || "Không thể xóa node. Vui lòng thử lại sau.");
      }
    };

    return (
      <div>
        <div
          className={cn(
            "flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/50 group transition-colors",
            depth > 0 && "ml-4"
          )}
        >
          {children.length > 0 ? (
            <button onClick={() => setOpen(v => !v)} className="text-slate-400 flex-shrink-0">
              {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
          ) : (
            <span className="w-3.5 h-3.5 flex-shrink-0" />
          )}
          <BookOpen className="w-3.5 h-3.5 text-violet-500 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
              {node.name_vi || node.name}
            </p>
            {node.chunk_count > 0 && (
              <p className="text-xs text-slate-400">{node.chunk_count} chunks</p>
            )}
          </div>
          <span className={cn(
            "text-xs px-2 py-0.5 rounded-full flex-shrink-0",
            node.chunk_count > 0
              ? "bg-green-50 dark:bg-green-950/30 text-green-600 dark:text-green-400 border border-green-200 dark:border-green-800"
              : "bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
          )}>
            {node.chunk_count > 0 ? "Có tài liệu" : "Chưa có tài liệu"}
          </span>
          <button
            onClick={() => setShowContentPicker(!showContentPicker)}
            className="text-xs px-2 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 rounded transition-all"
            title="Liên kết tài liệu với node"
          >
            📎 Liên kết
          </button>
          <button
            onClick={handleDeleteNode}
            className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
            title="Xóa node"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
        {/* Content picker modal */}
        {showContentPicker && (
          <ContentPickerModal
            courseId={courseId}
            onSelect={handleLinkContent}
            onClose={() => setShowContentPicker(false)}
            isLoading={processing}
          />
        )}
        {open && children.map(child => (
          <NodeRow key={child.id} node={child} depth={depth + 1} />
        ))}
      </div>
    );
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300"
        >
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          Knowledge Nodes ({nodes.length})
        </button>
        <div className="flex items-center gap-2">
          {/* View Mode Toggle */}
          {nodes.length > 0 && expanded && (
            <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1">
              <button
                onClick={() => setViewMode("graph")}
                className={cn(
                  "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md transition-all",
                  viewMode === "graph"
                    ? "bg-violet-600 text-white shadow-md"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                )}
              >
                <Network className="w-3.5 h-3.5" /> Graph
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={cn(
                  "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md transition-all",
                  viewMode === "list"
                    ? "bg-violet-600 text-white shadow-md"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                )}
              >
                <BookOpen className="w-3.5 h-3.5" /> List
              </button>
            </div>
          )}
          <button
            onClick={() => setConsolidateOpen(true)}
            disabled={nodes.length < 5}
            title={
              nodes.length < 5
                ? "Cần ít nhất 5 nodes để chạy hợp nhất"
                : "AI sẽ phân tích và gộp các node trùng lặp"
            }
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-gradient-to-r from-violet-500 to-fuchsia-500 hover:from-violet-600 hover:to-fuchsia-600 text-white rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Sparkles className="w-3.5 h-3.5" /> Làm gọn Graph
          </button>
          <button
            onClick={() => { setCreating(v => !v); setError(""); }}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg transition-all"
          >
            <Plus className="w-3.5 h-3.5" /> Thêm Node
          </button>
        </div>
      </div>

      <GraphConsolidateModal
        courseId={courseId}
        open={consolidateOpen}
        onClose={() => setConsolidateOpen(false)}
        onCompleted={() => {
          setConsolidateOpen(false);
          onNodesChange();
        }}
      />

      {/* Create form */}
      {creating && (
        <div className="bg-violet-50 dark:bg-violet-950/20 border border-violet-200 dark:border-violet-800 rounded-xl p-4 space-y-3">
          <p className="text-xs font-semibold text-violet-700 dark:text-violet-400 uppercase tracking-wide">
            Tạo Knowledge Node mới
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-600 dark:text-slate-400 mb-1">Tên EN *</label>
              <input
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="Dynamic Array"
                className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-600 dark:text-slate-400 mb-1">Tên VI</label>
              <input
                value={form.name_vi}
                onChange={e => setForm(f => ({ ...f, name_vi: e.target.value }))}
                placeholder="Mảng động"
                className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-600 dark:text-slate-400 mb-1">Mô tả</label>
            <input
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Kiến thức về mảng động trong lập trình..."
              className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400"
            />
          </div>
          {nodes.length > 0 && (
            <div>
              <label className="block text-xs text-slate-600 dark:text-slate-400 mb-1">
                Node cha (optional)
              </label>
              <select
                value={form.parent_id}
                onChange={e => setForm(f => ({ ...f, parent_id: e.target.value }))}
                className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                <option value="">— Root node —</option>
                {nodes.map(n => (
                  <option key={n.id} value={n.id}>{n.name_vi || n.name}</option>
                ))}
              </select>
            </div>
          )}
          {error && (
            <div className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              {error}
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              disabled={saving}
              className="flex-1 py-2 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-lg transition-all disabled:opacity-50"
            >
              {saving ? "Đang tạo…" : "Tạo Node"}
            </button>
            <button
              onClick={() => { setCreating(false); setError(""); }}
              className="px-4 py-2 border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 text-sm rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-all"
            >
              Hủy
            </button>
          </div>
        </div>
      )}

      {/* Main Content Area: List vs Graph */}
      {expanded && (
        <div className="mt-4 transition-all duration-300 ease-in-out">
          {nodes.length === 0 ? (
            <div className="text-center py-8 bg-slate-50 dark:bg-slate-800/30 rounded-xl border border-dashed border-slate-300 dark:border-slate-700">
              <Network className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Chưa có Knowledge Node nào.
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Tạo node rồi liên kết tài liệu để AI có thể thiết lập ma trận kiến thức.
              </p>
            </div>
          ) : viewMode === "graph" ? (
            // Bọc bằng một thẻ div có độ cao min-h-[600px] để panel mở ra không bị chật
            <div className="min-h-[600px] rounded-xl overflow-hidden border border-slate-200 dark:border-slate-800">
              <KnowledgeGraph
                courseId={courseId}
                initialData={graphData} // Truyền dữ liệu dạng Graph Data (Nodes + Links)
              />
            </div>
          ) : (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-2 overflow-hidden shadow-sm">
              {rootNodes.map(node => (
                <NodeRow key={node.id} node={node} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Warning Alert */}
      {nodes.some(n => n.chunk_count === 0) && (
        <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-xl text-xs text-amber-700 dark:text-amber-400 mt-4">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p>
            Một số node chưa có tài liệu. Hãy upload PDF/video vào phần <strong>Nội dung</strong> 
            và liên kết với node tương ứng để AI có context tạo bài giảng/quiz.
          </p>
        </div>
      )}
    </div>
  );
}