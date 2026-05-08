"use client";

import React, { useEffect, useState } from "react";
import { fetchRoles, deleteRole, fetchPermissions, fetchLmsRoleMappings, Role, Permission } from "@/lib/admin/rolesApi";
import { Loader2, Plus, Edit2, Trash2, Shield, Settings2, RefreshCcw } from "lucide-react";
import RoleModal from "./RoleModal";
import LmsMappingModal from "./LmsMappingModal";

export default function RoleManager() {
  const [roles, setRoles] = useState<Role[]>([]);

  const [lmsMappings, setLmsMappings] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);

  const [isMappingModalOpen, setIsMappingModalOpen] = useState(false);
  const [mappingRole, setMappingRole] = useState<Role | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [rData, pData, mData] = await Promise.all([
        fetchRoles(),
        fetchPermissions(),
        fetchLmsRoleMappings(),
      ]);
      setRoles(rData);
      setLmsMappings(mData);
    } catch (err: any) {
      setError(err.message || "Failed to load roles data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleDelete = async (role: Role) => {
    if (role.isSystem) {
      alert("Cannot delete system roles.");
      return;
    }
    if (!confirm(`Are you sure you want to delete the role ${role.name}?`)) return;

    try {
      await deleteRole(role.id);
      await loadData();
    } catch (err: any) {
      alert("Failed to delete role: " + err.message);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 text-red-600 rounded-xl border border-red-200 flex items-center justify-between">
        <p><strong>Error:</strong> {error}</p>
        <button onClick={loadData} className="p-2 bg-red-100 hover:bg-red-200 rounded-lg transition-colors">
          <RefreshCcw className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2">
            <Shield className="w-6 h-6 text-blue-500" />
            Role & Access Management
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Configure dynamic roles, permissions, and LMS service mappings.
          </p>
        </div>
        <button
          onClick={() => {
            setEditingRole(null);
            setIsRoleModalOpen(true);
          }}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-medium transition-all duration-200 shadow-sm shadow-blue-600/20 active:scale-95"
        >
          <Plus className="w-4 h-4" />
          Create New Role
        </button>
      </div>

      {/* Data Table */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800 text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
                <th className="px-6 py-4">Role Name</th>
                <th className="px-6 py-4">Display Name</th>
                <th className="px-6 py-4">Type</th>
                <th className="px-6 py-4">LMS Mappings</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {roles.map((role) => (
                <tr key={role.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono font-bold bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                      {role.name}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <p className="font-medium text-slate-900 dark:text-slate-50">{role.displayName}</p>
                    {role.description && (
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-1">{role.description}</p>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {role.isSystem ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
                        System
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                        Custom
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {lmsMappings[role.name]?.map((lmsRole) => (
                        <span key={lmsRole} className="px-2 py-0.5 text-xs font-medium rounded-md bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 border border-purple-200 dark:border-purple-800/50">
                          {lmsRole}
                        </span>
                      ))}
                      {(!lmsMappings[role.name] || lmsMappings[role.name].length === 0) && (
                        <span className="text-xs text-slate-400 italic">None</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => {
                          setMappingRole(role);
                          setIsMappingModalOpen(true);
                        }}
                        className="p-2 text-slate-400 hover:text-purple-600 dark:hover:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded-lg transition-colors"
                        title="Configure LMS Mappings"
                      >
                        <Settings2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          setEditingRole(role);
                          setIsRoleModalOpen(true);
                        }}
                        className="p-2 text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                        title="Edit Role"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(role)}
                        disabled={role.isSystem}
                        className="p-2 text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
                        title={role.isSystem ? "Cannot delete system role" : "Delete Role"}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {isRoleModalOpen && (
        <RoleModal
          role={editingRole}
          onClose={() => setIsRoleModalOpen(false)}
          onSuccess={loadData}
        />
      )}

      {isMappingModalOpen && mappingRole && (
        <LmsMappingModal
          role={mappingRole}
          currentMappings={lmsMappings[mappingRole.name] || []}
          onClose={() => setIsMappingModalOpen(false)}
          onSuccess={loadData}
        />
      )}
    </div>
  );
}
