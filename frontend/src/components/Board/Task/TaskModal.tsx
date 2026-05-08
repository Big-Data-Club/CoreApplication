"use client";

import React, { useState, useEffect } from "react";
import { Plus, X, ExternalLink, AlertCircle } from "lucide-react";
import { Task, User, EventItem } from "@/types";
import { formatDateForInput } from "@/utils/utils";
import { useAuth } from "@/hooks/useAuth";

interface TaskModalProps {
  task: Task | null;
  columnId: string | null;
  users: User[];
  events: EventItem[];
  onSave: (taskData: any) => Promise<void>;
  onClose: () => void;
}

const inputClass =
  "w-full border border-slate-300 dark:border-slate-700 rounded-xl px-4 py-3 " +
  "text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-600 " +
  "bg-slate-50 dark:bg-slate-800 " +
  "focus:bg-white dark:focus:bg-slate-900 " +
  "focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 " +
  "transition-all text-sm";

const labelClass = "block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2";

const TaskModal: React.FC<TaskModalProps> = ({ task, columnId, users, events, onSave, onClose }) => {
  const { canEditTask, checkTaskEditAccess } = useAuth();
  const [formData, setFormData] = useState({
    title: "",
    description: "",
    priority: "MEDIUM" as "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
    assignees: [] as (number | string)[],
    links: [] as { id: number | string; url: string; title: string }[],
    startDate: "",
    endDate: "",
    columnId: columnId || "todo",
    eventId: undefined as number | undefined,
  });
  const [newLink, setNewLink] = useState({ url: "", title: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assigneeSearch, setAssigneeSearch] = useState("");

  useEffect(() => {
    if (task) {
      setFormData({
        title: task.title,
        description: task.description,
        priority: task.priority || "MEDIUM",
        assignees: task.assignees,
        links: task.links || [],
        startDate: task.startDate ? formatDateForInput(task.startDate) : "",
        endDate: task.endDate ? formatDateForInput(task.endDate) : "",
        columnId: task.columnId,
        eventId: task.eventId ? Number(task.eventId) : undefined,
      });
    }
  }, [task]);

  const handleAddLink = () => {
    if (newLink.url && newLink.title) {
      setFormData({ ...formData, links: [...formData.links, { id: Date.now(), ...newLink }] });
      setNewLink({ url: "", title: "" });
    }
  };

  const handleRemoveLink = (linkId: number | string) =>
    setFormData({ ...formData, links: formData.links.filter((l) => l.id !== linkId) });

  const toggleAssignee = (userId: number | string) => {
    const assigned = formData.assignees.some((id) => id.toString() === userId.toString());
    setFormData({
      ...formData,
      assignees: assigned
        ? formData.assignees.filter((id) => id.toString() !== userId.toString())
        : [...formData.assignees, userId],
    });
  };

  const handleSubmit = async () => {
    if (!formData.title.trim()) { setError("Task title is required"); return; }
    if (formData.startDate && formData.endDate && new Date(formData.endDate) < new Date(formData.startDate)) {
      setError("End date must be after start date"); return;
    }
    if (!checkTaskEditAccess()) {
      setError("Bạn không có quyền chỉnh sửa task. Chỉ Admin hoặc Manager mới được phép."); return;
    }

    setSaving(true);
    setError(null);
    try {
      await onSave(formData);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to save task");
    } finally {
      setSaving(false);
    }
  };

  const sortedAndFilteredUsers = React.useMemo(() => {
    const active = users.filter((u) => u.status !== false && u.active !== false);
    const filtered = active.filter(
      (u) =>
        u.name.toLowerCase().includes(assigneeSearch.toLowerCase()) ||
        u.code.toLowerCase().includes(assigneeSearch.toLowerCase())
    );
    
    return filtered.sort((a, b) => {
      const aAssigned = formData.assignees.some((id) => id.toString() === a.id.toString());
      const bAssigned = formData.assignees.some((id) => id.toString() === b.id.toString());
      if (aAssigned && !bAssigned) return -1;
      if (!aAssigned && bAssigned) return 1;
      return a.name.localeCompare(b.name);
    });
  }, [users, assigneeSearch, formData.assignees]);

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">

          {/* Header */}
          <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-100 dark:border-slate-800">
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-50">
              {task ? "Edit Task" : "New Task"}
            </h2>
            <button
              onClick={onClose}
              disabled={saving}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-5 p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl text-red-600 dark:text-red-400 text-sm flex items-start gap-2">
              <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          <div className="space-y-5">
            {/* Title */}
            <div>
              <label className={labelClass}>
                Task Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className={inputClass}
                placeholder="Enter task title..."
              />
            </div>

            {/* Description */}
            <div>
              <label className={labelClass}>Description</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className={inputClass + " resize-none"}
                rows={4}
                placeholder="Enter task description..."
              />
            </div>

            {/* Priority + Status row */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelClass}>Priority</label>
                <select
                  value={formData.priority}
                  onChange={(e) => setFormData({ ...formData, priority: e.target.value as any })}
                  className={inputClass}
                >
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                  <option value="CRITICAL">Critical</option>
                </select>
              </div>
              <div>
                <label className={labelClass}>Status</label>
                <select
                  value={formData.columnId}
                  onChange={(e) => setFormData({ ...formData, columnId: e.target.value })}
                  className={inputClass}
                >
                  <option value="todo">TODO</option>
                  <option value="in-progress">In Progress</option>
                  <option value="done">Done</option>
                  <option value="cancel">Cancel</option>
                </select>
              </div>
            </div>

            {/* Event */}
            <div>
              <label className={labelClass}>Event</label>
              <select
                value={formData.eventId || ""}
                onChange={(e) =>
                  setFormData({ ...formData, eventId: e.target.value ? Number(e.target.value) : undefined })
                }
                className={inputClass}
              >
                <option value="">No Event</option>
                {events.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.title}
                    {event.startTime &&
                      ` (${new Date(event.startTime).toLocaleDateString("vi-VN")}${event.endTime ? " – " + new Date(event.endTime).toLocaleDateString("vi-VN") : ""})`}
                  </option>
                ))}
              </select>
            </div>

            {/* Assignees */}
            <div>
              <label className={labelClass}>Assignees</label>
              <input
                type="text"
                value={assigneeSearch}
                onChange={(e) => setAssigneeSearch(e.target.value)}
                className={inputClass + " mb-2"}
                placeholder="Search by name or code..."
              />
              <div className="space-y-1 max-h-40 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-xl p-3 bg-slate-50 dark:bg-slate-800">
                {sortedAndFilteredUsers.length > 0 ? (
                  sortedAndFilteredUsers.map((user) => (
                    <label
                      key={user.id}
                      className="flex items-center gap-3 p-2 hover:bg-white dark:hover:bg-slate-700 rounded-lg cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={formData.assignees.some((id) => id.toString() === user.id.toString())}
                        onChange={() => toggleAssignee(user.id)}
                        className="rounded text-blue-600 focus:ring-blue-500/20 border-slate-300 dark:border-slate-600"
                      />
                      <span className="text-sm text-slate-700 dark:text-slate-300">
                        {user.name}{" "}
                        <span className="text-slate-400 dark:text-slate-500">
                          ({user.team}) · {user.code}
                        </span>
                      </span>
                    </label>
                  ))
                ) : (
                  <p className="text-sm text-slate-400 dark:text-slate-600 text-center py-3">
                    No users found
                  </p>
                )}
              </div>
            </div>

            {/* Links */}
            <div>
              <label className={labelClass}>Links</label>
              <div className="space-y-2 mb-2">
                {formData.links.map((link) => (
                  <div
                    key={link.id}
                    className="flex items-center gap-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-2.5 rounded-xl"
                  >
                    <ExternalLink size={13} className="text-slate-400 flex-shrink-0" />
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 text-sm text-blue-600 dark:text-blue-400 hover:underline truncate"
                    >
                      {link.title}
                    </a>
                    <button
                      onClick={() => handleRemoveLink(link.id)}
                      type="button"
                      className="text-red-400 hover:text-red-600 dark:hover:text-red-300 transition-colors"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newLink.title}
                  onChange={(e) => setNewLink({ ...newLink, title: e.target.value })}
                  className={inputClass + " flex-1"}
                  placeholder="Link title..."
                />
                <input
                  type="url"
                  value={newLink.url}
                  onChange={(e) => setNewLink({ ...newLink, url: e.target.value })}
                  className={inputClass + " flex-1"}
                  placeholder="https://..."
                />
                <button
                  onClick={handleAddLink}
                  type="button"
                  className="bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-3 transition-all active:scale-95"
                >
                  <Plus size={16} />
                </button>
              </div>
            </div>

            {/* Dates */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelClass}>Start Date</label>
                <input
                  type="datetime-local"
                  value={formData.startDate}
                  onChange={(e) => setFormData({ ...formData, startDate: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>End Date</label>
                <input
                  type="datetime-local"
                  value={formData.endDate}
                  onChange={(e) => setFormData({ ...formData, endDate: e.target.value })}
                  className={inputClass}
                />
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex gap-3 mt-8 pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              onClick={handleSubmit}
              disabled={saving || !canEditTask}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl py-2.5 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {saving ? "Saving..." : "Save Task"}
            </button>
            <button
              onClick={onClose}
              disabled={saving}
              className="px-5 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700
                         text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800
                         rounded-xl font-medium transition-all active:scale-95 disabled:opacity-50 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TaskModal;