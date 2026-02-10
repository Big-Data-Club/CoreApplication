"use client";

import React, { useState, useEffect } from "react";
import { Plus, X, ExternalLink } from "lucide-react";
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

const TaskModal: React.FC<TaskModalProps> = ({
  task,
  columnId,
  users,
  events,
  onSave,
  onClose,
}) => {
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
      setFormData({
        ...formData,
        links: [
          ...formData.links,
          { id: Date.now(), url: newLink.url, title: newLink.title },
        ],
      });
      setNewLink({ url: "", title: "" });
    }
  };

  const handleRemoveLink = (linkId: number | string) => {
    setFormData({
      ...formData,
      links: formData.links.filter((l) => l.id !== linkId),
    });
  };

  const toggleAssignee = (userId: number | string) => {
    const isAssigned = formData.assignees.some(
      (id) => id.toString() === userId.toString()
    );
    setFormData({
      ...formData,
      assignees: isAssigned
        ? formData.assignees.filter((id) => id.toString() !== userId.toString())
        : [...formData.assignees, userId],
    });
  };

  const handleSubmit = async () => {
    if (!formData.title.trim()) {
      setError("Task title is required");
      return;
    }

    if (formData.startDate && formData.endDate && new Date(formData.endDate) < new Date(formData.startDate)) {
      setError("End date must be after start date");
      return;
    }

    if (!checkTaskEditAccess()) {
      setError("Bạn không có quyền chỉnh sửa task. Chỉ Admin hoặc Manager mới được phép.");
      return;
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

  // Filter active users
  const activeUsers = users.filter((u) => u.status !== false && u.active !== false);

  // Filtered assignees based on search
  const filteredUsers = activeUsers.filter((user) =>
    user.name.toLowerCase().includes(assigneeSearch.toLowerCase()) ||
    user.code.toLowerCase().includes(assigneeSearch.toLowerCase())
  );

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-gray-800">
              {task ? "Edit Task" : "New Task"}
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600"
              disabled={saving}
            >
              <X size={24} />
            </button>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-6">
            {/* Title */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Task Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) =>
                  setFormData({ ...formData, title: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Enter task title..."
                required
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Description
              </label>
              <textarea
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                rows={4}
                placeholder="Enter task description..."
              />
            </div>

            {/* Priority */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Priority
              </label>
              <select
                value={formData.priority}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    priority: e.target.value as any,
                  })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="CRITICAL">Critical</option>
              </select>
            </div>

            {/* Event */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Event
              </label>
              <select
                value={formData.eventId || ""}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    eventId: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">No Event</option>
                {events.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.title} (
                    {event.startTime &&
                      new Date(event.startTime).toLocaleDateString("vi-VN")}
                    {event.startTime && event.endTime && " - "}
                    {event.endTime &&
                      new Date(event.endTime).toLocaleDateString("vi-VN")}
                    )
                  </option>
                ))}
              </select>
            </div>

            {/* Column Status */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Status
              </label>
              <select
                value={formData.columnId}
                onChange={(e) =>
                  setFormData({ ...formData, columnId: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="todo">TODO</option>
                <option value="in-progress">In Progress</option>
                <option value="done">Done</option>
                <option value="cancel">Cancel</option>
              </select>
            </div>

            {/* Assignees */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Assignees
              </label>
              <input
                type="text"
                value={assigneeSearch}
                onChange={(e) => setAssigneeSearch(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent mb-3"
                placeholder="Search by name or code..."
              />
              <div className="space-y-2 max-h-40 overflow-y-auto border border-gray-200 rounded-lg p-3">
                {filteredUsers.length > 0 ? (
                  filteredUsers.map((user) => (
                    <label
                      key={user.id}
                      className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={formData.assignees.some(
                          (id) => id.toString() === user.id.toString()
                        )}
                        onChange={() => toggleAssignee(user.id)}
                        className="rounded text-blue-500 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-700">
                        {user.name} ({user.team}) - {user.code}
                      </span>
                    </label>
                  ))
                ) : (
                  <p className="text-sm text-gray-500 text-center py-2">
                    No users found
                  </p>
                )}
              </div>
            </div>

            {/* Links */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Links
              </label>
              <div className="space-y-3">
                {formData.links.map((link) => (
                  <div
                    key={link.id}
                    className="flex items-center gap-2 bg-gray-50 p-2 rounded"
                  >
                    <ExternalLink size={16} className="text-gray-400" />
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 text-sm text-blue-600 hover:underline truncate"
                    >
                      {link.title}
                    </a>
                    <button
                      onClick={() => handleRemoveLink(link.id)}
                      className="text-red-500 hover:text-red-700"
                      type="button"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))}

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newLink.title}
                    onChange={(e) =>
                      setNewLink({ ...newLink, title: e.target.value })
                    }
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Link title..."
                  />
                  <input
                    type="url"
                    value={newLink.url}
                    onChange={(e) =>
                      setNewLink({ ...newLink, url: e.target.value })
                    }
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="URL..."
                  />
                  <button
                    onClick={handleAddLink}
                    type="button"
                    className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
                  >
                    <Plus size={16} />
                  </button>
                </div>
              </div>
            </div>

            {/* Dates */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Start Date
                </label>
                <input
                  type="datetime-local"
                  value={formData.startDate}
                  onChange={(e) =>
                    setFormData({ ...formData, startDate: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  End Date
                </label>
                <input
                  type="datetime-local"
                  value={formData.endDate}
                  onChange={(e) =>
                    setFormData({ ...formData, endDate: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            </div>
          </div>

          {/* Footer Buttons */}
          <div className="flex gap-3 mt-8">
            <button
              onClick={handleSubmit}
              disabled={saving || !canEditTask}
              className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? "Saving..." : "Save Task"}
            </button>
            <button
              onClick={onClose}
              disabled={saving}
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
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