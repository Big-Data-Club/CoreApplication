"use client";

import React, { useEffect, useState } from "react";
import { adminLmsService, UserRoleDetail, RoleDefinition } from "@/services/adminLmsService";
import { Shield, Plus, Trash2, Loader2, Info, CheckCircle2, History } from "lucide-react";
import { cn } from "@/lib/utils";

interface LmsUserRoleManagerProps {
  userId: number | string;
}

export default function LmsUserRoleManager({ userId }: LmsUserRoleManagerProps) {
  const [userRoles, setUserRoles] = useState<UserRoleDetail[]>([]);
  const [allRoles, setAllRoles] = useState<RoleDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState("");

  const loadData = async () => {
    try {
      setLoading(true);
      const [uRoles, aRoles] = await Promise.all([
        adminLmsService.getUserRoles(userId),
        adminLmsService.listRoles(),
      ]);
      setUserRoles(uRoles || []);
      setAllRoles(aRoles || []);
    } catch (err: any) {
      setError(err.message || "Failed to load LMS roles");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [userId]);

  const handleAssign = async () => {
    if (!selectedRole) return;
    try {
      setActionLoading("assigning");
      await adminLmsService.assignRole(userId, selectedRole);
      await loadData();
      setSelectedRole("");
    } catch (err: any) {
      alert("Gán role thất bại: " + err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRemove = async (roleName: string) => {
    if (!confirm(`Bạn có chắc muốn gỡ role ${roleName} khỏi user này?`)) return;
    try {
      setActionLoading(roleName);
      await adminLmsService.removeRole(userId, roleName);
      await loadData();
    } catch (err: any) {
      alert("Gỡ role thất bại: " + err.message);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-10 space-y-3">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        <p className="text-sm text-slate-500">Đang tải phân quyền LMS...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2">
          <Shield className="w-4 h-4 text-blue-500" />
          LMS Access Control
        </h4>
        <div className="px-2 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-[10px] font-bold text-blue-600 dark:text-blue-400 rounded uppercase tracking-wider">
          Per-User Management
        </div>
      </div>

      {/* Info Box */}
      <div className="p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/50 rounded-xl flex gap-3">
        <Info className="w-4 h-4 text-amber-600 dark:text-amber-500 mt-0.5 shrink-0" />
        <p className="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
          <b>Synced</b> roles are automatically updated from the main Role Mappings. 
          <b>Manual</b> roles are overrides that persist even after synchronization.
        </p>
      </div>

      {/* Role List */}
      <div className="space-y-3">
        <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
          Current LMS Roles
        </label>
        
        {userRoles.length === 0 ? (
          <div className="text-center py-6 border-2 border-dashed border-slate-100 dark:border-slate-800 rounded-2xl">
            <p className="text-sm text-slate-400 italic">No LMS roles assigned.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2">
            {userRoles.map((ur) => (
              <div 
                key={ur.role}
                className="flex items-center justify-between p-3 bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl hover:shadow-sm transition-shadow"
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "p-2 rounded-lg",
                    ur.source === "sync" ? "bg-slate-100 dark:bg-slate-800 text-slate-600" : "bg-blue-50 dark:bg-blue-900/40 text-blue-600"
                  )}>
                    <Shield className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-900 dark:text-slate-50">{ur.role}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      {ur.source === "sync" ? (
                        <span className="flex items-center gap-1 text-[10px] font-medium text-slate-500">
                          <CheckCircle2 className="w-3 h-3" /> Synced from Global
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[10px] font-medium text-blue-500">
                          <History className="w-3 h-3" /> Manually Assigned
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {ur.source === "manual" && (
                  <button
                    onClick={() => handleRemove(ur.role)}
                    disabled={actionLoading !== null}
                    className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 rounded-lg transition-colors disabled:opacity-50"
                    title="Remove manual role"
                  >
                    {actionLoading === ur.role ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4" />
                    )}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Assignment Form */}
      <div className="pt-4 border-t border-slate-100 dark:border-slate-800">
        <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
          Assign New LMS Role
        </label>
        <div className="flex gap-2">
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            className="flex-1 px-3.5 py-2 border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
          >
            <option value="">Select a role...</option>
            {allRoles
              .filter(r => !userRoles.some(ur => ur.role === r.name))
              .map(r => (
                <option key={r.id} value={r.name}>{r.display_name} ({r.name})</option>
              ))
            }
            {/* Fallback common roles if definitions not loaded */}
            {!allRoles.some(r => r.name === "STUDENT") && !userRoles.some(ur => ur.role === "STUDENT") && <option value="STUDENT">STUDENT</option>}
            {!allRoles.some(r => r.name === "TEACHER") && !userRoles.some(ur => ur.role === "TEACHER") && <option value="TEACHER">TEACHER</option>}
            {!allRoles.some(r => r.name === "ADMIN") && !userRoles.some(ur => ur.role === "ADMIN") && <option value="ADMIN">ADMIN</option>}
          </select>
          <button
            onClick={handleAssign}
            disabled={!selectedRole || actionLoading !== null}
            className="flex items-center gap-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold text-sm transition-all active:scale-95 disabled:opacity-50"
          >
            {actionLoading === "assigning" ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Assign
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
