"use client";

import React, { useCallback, useEffect, useState } from "react";
import { userService, UserResponse } from "@/services/userService";

interface PendingUsersSectionProps {
  isAdmin: boolean;
  onApproved?: () => void;
}

export function PendingUsersSection({ isAdmin, onApproved }: PendingUsersSectionProps) {
  const [pending, setPending] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const loadPending = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const list = await userService.getPendingUsers();
      setPending(list);
    } catch {
      setPending([]);
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadPending();
  }, [loadPending]);

  const handleApprove = async (id: number) => {
    if (!confirm("Duyệt tài khoản này? Mật khẩu sẽ được gửi qua email.")) return;
    setActionLoading(id);
    try {
      await userService.approveUser(id);
      await loadPending();
      onApproved?.();
    } catch (err: any) {
      alert("Duyệt thất bại: " + (err.message || err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: number) => {
    if (!confirm("Từ chối tài khoản này? Tài khoản sẽ bị khóa.")) return;
    setActionLoading(id);
    try {
      await userService.rejectUser(id);
      await loadPending();
    } catch (err: any) {
      alert("Từ chối thất bại: " + (err.message || err));
    } finally {
      setActionLoading(null);
    }
  };

  if (!isAdmin || pending.length === 0) return null;

  return (
    <div className="mb-8">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-xl font-bold text-slate-900 dark:text-slate-50">
          Chờ duyệt
        </h2>
        <span className="inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
          {pending.length}
        </span>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-amber-200 dark:border-amber-800 overflow-hidden">
        {loading ? (
          <div className="py-8 text-center">
            <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-amber-500" />
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {pending.map((user) => (
              <div
                key={user.id}
                className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-5 py-4 gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {user.profilePicture ? (
                    <img
                      src={user.profilePicture}
                      alt={user.name}
                      className="w-10 h-10 rounded-full border border-slate-200 dark:border-slate-700"
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/40 flex items-center justify-center text-blue-600 dark:text-blue-400 font-bold text-sm">
                      {user.name?.charAt(0)?.toUpperCase() || "?"}
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="font-semibold text-slate-900 dark:text-slate-50 truncate">
                      {user.name}
                    </p>
                    <p className="text-sm text-slate-500 dark:text-slate-400 truncate">
                      {user.email} · {user.code} · {user.team} · {user.type}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleApprove(user.id)}
                    disabled={actionLoading === user.id}
                    className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold transition-all active:scale-95 disabled:opacity-50"
                  >
                    {actionLoading === user.id ? "..." : "Duyệt"}
                  </button>
                  <button
                    onClick={() => handleReject(user.id)}
                    disabled={actionLoading === user.id}
                    className="px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 text-sm font-semibold hover:bg-red-50 dark:hover:bg-red-950/30 transition-all active:scale-95 disabled:opacity-50"
                  >
                    Từ chối
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
