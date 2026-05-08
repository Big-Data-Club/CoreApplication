"use client";

import React, { useState, useEffect } from "react";
import { X, Plus, Trash2, Save, Check, Award, AlertCircle, Loader2 } from "lucide-react";
import { Task, User } from "@/types";
import { taskScoreService, TaskScoreResponse } from "@/services/taskScoreService";
import { useAuth } from "@/hooks/useAuth";

interface TaskScoreModalProps {
  task: Task;
  users: User[];
  isOpen: boolean;
  onClose: () => void;
  currentUserId: number;
  onScoresUpdated?: () => void;
}

const inputClass =
  "border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-2 " +
  "text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-600 " +
  "bg-slate-50 dark:bg-slate-800 " +
  "focus:bg-white dark:focus:bg-slate-900 " +
  "focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 " +
  "transition-all text-sm";

const labelClass = "block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5";

const TaskScoreModal: React.FC<TaskScoreModalProps> = ({
  task, users, isOpen, onClose, currentUserId, onScoresUpdated,
}) => {
  const { isAdmin, isManager } = useAuth();
  const [scores, setScores] = useState<TaskScoreResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingScore, setEditingScore] = useState<{ userId: number; score: number } | null>(null);
  const [deductingScore, setDeductingScore] = useState<{
    userId: number; amount: number; reason: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [userSearch, setUserSearch] = useState("");
  const [lastScoredUserId, setLastScoredUserId] = useState<number | null>(null);

  const canManageScores = isAdmin || isManager;
  const assignedUserIds = task?.assignees || [];
  const taskAssignees = React.useMemo(() => {
    const list = users.filter((u) =>
      assignedUserIds.some((id) => id.toString() === u.id.toString())
    );
    
    // Filter by search
    const filtered = list.filter(u => 
      u.name.toLowerCase().includes(userSearch.toLowerCase()) ||
      u.code.toLowerCase().includes(userSearch.toLowerCase())
    );

    // Sort: last scored first, then by name
    return filtered.sort((a, b) => {
      if (a.id === lastScoredUserId) return -1;
      if (b.id === lastScoredUserId) return 1;
      return a.name.localeCompare(b.name);
    });
  }, [users, assignedUserIds, userSearch, lastScoredUserId]);

  useEffect(() => {
    if (isOpen && task?.id) loadScores();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, task?.id]);

  const withLoading = async (fn: () => Promise<void>) => {
    try { setLoading(true); await fn(); setError(null); }
    catch (err) { setError("Operation failed. Please try again."); console.error(err); }
    finally { setLoading(false); }
  };

  const loadScores = () =>
    withLoading(async () => {
      const data = await taskScoreService.getTaskScores(task.id as number);
      setScores(data);
    });

  const handleSetScore = (userId: number, score: number) =>
    withLoading(async () => {
      const resp = await taskScoreService.setScore({ taskId: task.id as number, userId, score, notes: "Set by admin/manager" }, currentUserId);
      setScores(prev => {
        const existing = prev.findIndex(s => s.userId === userId);
        if (existing > -1) {
          const next = [...prev];
          next[existing] = { ...next[existing], score };
          return next;
        }
        return [...prev, resp];
      });
      setLastScoredUserId(userId);
      setEditingScore(null);
    });

  const handleDeductScore = () =>
    deductingScore
      ? withLoading(async () => {
          await taskScoreService.deductScore(task.id as number, deductingScore.userId, deductingScore.amount, deductingScore.reason, currentUserId);
          await loadScores();
          setDeductingScore(null);
        })
      : Promise.resolve();

  const handleToggleApply = (userId: number, currentApplied: boolean) =>
    withLoading(async () => {
      await taskScoreService.toggleApplyScore(task.id as number, userId, !currentApplied, currentUserId);
      await loadScores();
    });

  const handleApplyAllScores = () =>
    withLoading(async () => {
      await taskScoreService.applyScoresToTask(task.id as number, currentUserId);
      await loadScores();
      onScoresUpdated?.();
    });

  const handleDeleteScore = (userId: number) =>
    withLoading(async () => {
      if (!confirm("Are you sure you want to delete this score?")) return;
      await taskScoreService.deleteScore(task.id as number, userId, currentUserId);
      await loadScores();
    });

  const handleInitializeScores = () =>
    withLoading(async () => {
      const initialScore = prompt("Enter initial score for all assignees (e.g., 10)", "10");
      if (!initialScore) return;
      await taskScoreService.initializeScoresForTask(task.id as number, parseInt(initialScore), currentUserId);
      await loadScores();
    });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm max-w-2xl w-full mx-auto max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-2 rounded-xl">
              <Award className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-slate-50">Manage Scores</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 max-w-xs truncate">{task?.title}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">

          {/* Error */}
          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl text-red-600 dark:text-red-400 text-sm flex items-start gap-2">
              <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          {/* No-permission warning */}
          {!canManageScores && (
            <div className="p-3 bg-yellow-50 dark:bg-yellow-950/40 border border-yellow-200 dark:border-yellow-800 rounded-xl text-yellow-700 dark:text-yellow-400 text-sm">
              You do not have permission to manage scores. Only Admin and Manager can manage scores.
            </div>
          )}

          {/* Search */}
          <div className="relative">
            <input
              type="text"
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              placeholder="Search assigned users..."
              className={inputClass + " w-full"}
            />
          </div>

          {/* Action buttons */}
          {canManageScores && (
            <div className="flex gap-3 flex-wrap">
              <button
                onClick={handleInitializeScores}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700
                           text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800
                           rounded-xl font-medium text-sm transition-all active:scale-95 disabled:opacity-50"
              >
                <Plus size={15} /> Initialize Scores
              </button>
              <button
                onClick={handleApplyAllScores}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white
                           rounded-xl font-medium text-sm transition-all active:scale-95 disabled:opacity-50"
              >
                <Check size={15} /> Apply All Scores
              </button>
            </div>
          )}

          {/* Scores table */}
          {loading ? (
            <div className="text-center py-10">
              <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-2" />
              <p className="text-slate-500 dark:text-slate-400 text-sm">Loading scores...</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
                    <th className="text-left py-3 px-4 font-semibold text-slate-600 dark:text-slate-400">User</th>
                    <th className="text-center py-3 px-4 font-semibold text-slate-600 dark:text-slate-400">Score</th>
                    <th className="text-center py-3 px-4 font-semibold text-slate-600 dark:text-slate-400">Applied</th>
                    <th className="text-center py-3 px-4 font-semibold text-slate-600 dark:text-slate-400">Date</th>
                    <th className="text-center py-3 px-4 font-semibold text-slate-600 dark:text-slate-400">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {taskAssignees.map((assignee) => {
                    const userScore = scores.find((s) => s.userId === assignee.id);
                    const isEditing = editingScore?.userId === assignee.id;
                    const isDeducting = deductingScore?.userId === assignee.id;

                    return (
                      <tr key={assignee.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors">
                        {/* User */}
                        <td className="py-3 px-4">
                          <p className="font-medium text-slate-900 dark:text-slate-100">{assignee.name}</p>
                          <p className="text-xs text-slate-400 dark:text-slate-600">{assignee.code} · {assignee.team}</p>
                        </td>

                        {/* Score */}
                        <td className="py-3 px-4 text-center">
                          {isEditing ? (
                            <div className="flex gap-2 items-center justify-center">
                              <input
                                type="number"
                                value={editingScore.score}
                                onChange={(e) => setEditingScore({ ...editingScore, score: parseInt(e.target.value) || 0 })}
                                className={inputClass + " w-20 text-center"}
                              />
                              <button
                                onClick={() => handleSetScore(assignee.id as number, editingScore.score)}
                                className="text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300 p-1"
                              >
                                <Save size={15} />
                              </button>
                            </div>
                          ) : (
                            <span className="text-lg font-extrabold text-slate-900 dark:text-slate-100">
                              {userScore?.score ?? 0}
                            </span>
                          )}
                        </td>

                        {/* Applied badge */}
                        <td className="py-3 px-4 text-center">
                          {userScore?.applied ? (
                            <span className="inline-flex items-center gap-1 bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800 px-2.5 py-1 rounded-lg text-xs font-medium">
                              <Check size={11} /> Applied
                            </span>
                          ) : (
                            <span className="inline-block bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-500 px-2.5 py-1 rounded-lg text-xs font-medium">
                              Not Applied
                            </span>
                          )}
                        </td>

                        {/* Applied at */}
                        <td className="py-3 px-4 text-center text-xs text-slate-400 dark:text-slate-600">
                          {userScore?.appliedAt
                            ? new Date(userScore.appliedAt).toLocaleDateString("vi-VN")
                            : "—"}
                        </td>

                        {/* Actions */}
                        <td className="py-3 px-4 text-center">
                          {canManageScores && !isEditing && !isDeducting && (
                            <div className="flex gap-1 justify-center">
                              <button
                                onClick={() => setEditingScore({ userId: assignee.id as number, score: userScore?.score || 0 })}
                                className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950/40 transition-colors"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => handleToggleApply(assignee.id as number, userScore?.applied || false)}
                                className={`text-xs font-medium px-2 py-1 rounded-lg transition-colors ${
                                  userScore?.applied
                                    ? "text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40"
                                    : "text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/40"
                                }`}
                              >
                                {userScore?.applied ? "Unapply" : "Apply"}
                              </button>
                              <button
                                onClick={() => setDeductingScore({ userId: assignee.id as number, amount: 0, reason: "" })}
                                className="text-xs font-medium text-orange-500 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-950/40 px-2 py-1 rounded-lg transition-colors"
                              >
                                Deduct
                              </button>
                              <button
                                onClick={() => handleDeleteScore(assignee.id as number)}
                                className="text-red-400 dark:text-red-500 hover:text-red-600 dark:hover:text-red-300 p-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Deduct form */}
          {deductingScore && canManageScores && (
            <div className="border border-orange-200 dark:border-orange-800 rounded-2xl p-4 bg-orange-50 dark:bg-orange-950/30">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm mb-3">
                Deduct Score — {taskAssignees.find((u) => u.id === deductingScore.userId)?.name}
              </h3>
              <div className="space-y-3">
                <div>
                  <label className={labelClass}>Amount to Deduct</label>
                  <input
                    type="number"
                    value={deductingScore.amount}
                    onChange={(e) => setDeductingScore({ ...deductingScore, amount: parseInt(e.target.value) || 0 })}
                    className={inputClass + " w-full"}
                    min="0"
                  />
                </div>
                <div>
                  <label className={labelClass}>Reason</label>
                  <input
                    type="text"
                    value={deductingScore.reason}
                    onChange={(e) => setDeductingScore({ ...deductingScore, reason: e.target.value })}
                    placeholder="e.g., Late submission, incorrect work"
                    className={inputClass + " w-full"}
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleDeductScore}
                    disabled={loading || deductingScore.amount <= 0}
                    className="flex-1 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-medium text-sm transition-all active:scale-95 disabled:opacity-50"
                  >
                    Deduct Points
                  </button>
                  <button
                    onClick={() => setDeductingScore(null)}
                    className="flex-1 px-4 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700
                               text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800
                               rounded-xl font-medium text-sm transition-all active:scale-95"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-100 dark:border-slate-800 p-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2.5 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700
                       text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800
                       rounded-xl font-medium text-sm transition-all active:scale-95"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default TaskScoreModal;