"use client";
import React, { useEffect, useMemo, useState } from "react";
import { User } from "@/types";
import { fetchUsers, postBulkRegister, updateUserStatus } from "@/lib/users/api";
import { parseFile } from "@/lib/users/fileParser";
import UserRow from "./UserRow";
import DetailModal from "./DetailModal";
import { mapFrontendRoleToBackend, mapFrontendTeamToBackend, mapFrontendTypeToBackend } from "@/lib/users/auth";
import { useAuth } from "@/hooks/useAuth";
import { PendingUsersSection } from "./PendingUsersSection";

export default function UserApp() {
  const { isAdmin } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");

  const [detail, setDetail] = useState<User | null>(null);

  const [sortKey, setSortKey] = useState<"name" | "role" | "team" | "score" | "dateAdded" | "status" | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc" | null>(null);

  // simple sort toggler
  function toggleSort(key: typeof sortKey) {
    if (sortKey !== key) { setSortKey(key); setSortDir("asc"); return; }
    if (sortDir === "asc") setSortDir("desc");
    else if (sortDir === "desc") { setSortKey(null); setSortDir(null); }
    else setSortDir("asc");
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchUsers();
      setUsers(list);
    } catch (err: any) {
      console.error(err);
      setError(err?.message ?? String(err));
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleFilePicked(file?: File) {
    if (!file) return;
    try {
      const rows = await parseFile(file);
      if (!rows || rows.length === 0) {
        alert("No valid rows found in file");
        return;
      }
      // map to backend shape
      const payload = rows.map(r => ({
        name: r.name,
        email: r.email,
        role: mapFrontendRoleToBackend(r.role ?? "Member"),
        team: mapFrontendTeamToBackend(r.team ?? "Research"),
        code: r.code,
        type: mapFrontendTypeToBackend(r.type ?? "CLC"),
      }));
      const res = await postBulkRegister(payload);
      if (!res) {
        throw new Error("Fail to bulk regiter")
      }
      alert("Bulk create success");
      await load();
    } catch (err: any) {
      console.error(err);
      alert("Upload failed: " + (err.message || err));
    } finally {
      // clear file input outside
      const fileInput = document.getElementById("user-file-input") as HTMLInputElement | null;
      if (fileInput) fileInput.value = "";
    }
  }

  async function toggleStatusLocal(id: string | number) {
    if (!isAdmin) {
      alert("Chỉ có Quản trị viên mới có thể thực hiện hành động này.");
      return;
    }

    try {
      await updateUserStatus(id);
      await load();
    } catch (err: any) {
      console.error(err);
      alert("Cập nhật trạng thái thất bại: " + (err.message || err));
    }
  }

  const filteredAndSorted = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = users.filter(u => {
      if (teamFilter && u.team !== teamFilter) return false;
      if (typeFilter && u.type !== typeFilter) return false;
      if (roleFilter && u.role !== roleFilter) return false;
      if (!q) return true;
      return u.name.toLowerCase().includes(q) || u.code.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
    });
    if (sortKey && sortDir) {
      const dir = sortDir === "asc" ? 1 : -1;
      list = [...list].sort((a,b) => {
        switch (sortKey) {
          case "name": return a.name.localeCompare(b.name) * dir;
          case "role": return (a.role || "").localeCompare(b.role || "") * dir;
          case "team": return (a.team || "").localeCompare(b.team || "") * dir;
          case "score": return (Number(a.score) - Number(b.score)) * dir;
          case "dateAdded": return a.dateAdded && b.dateAdded ? (new Date(a.dateAdded).getTime() - new Date(b.dateAdded).getTime()) * dir : 0;
          case "status": return ((a.status?1:0) - (b.status?1:0)) * dir;
          default: return 0;
        }
      });
    }
    return list;
  }, [users, query, teamFilter, typeFilter, sortKey, sortDir]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 sm:p-6 lg:p-8">
      <div className="max-w-[1200px] mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="mb-6">
            <h1 className="text-3xl md:text-4xl font-extrabold text-slate-900 dark:text-slate-50 leading-tight mb-2">
              Users
            </h1>
            <p className="text-slate-600 dark:text-slate-400">
              {users.length} total users
            </p>
            {error && (
              <div className="mt-3 p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl">
                <p className="text-sm text-red-600 dark:text-red-400">
                  <strong>Error:</strong> {error}
                </p>
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-center lg:justify-between">
            {/* Search */}
            <div className="w-full lg:w-auto relative">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by name, email, or code..."
                className="w-full lg:w-80 px-4 py-2.5 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl text-slate-900 dark:text-slate-50 placeholder-slate-400 dark:placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
              />
            </div>

            {/* Filters & Actions */}
            <div className="flex flex-wrap gap-3 w-full lg:w-auto">
              {/* Team Filter */}
              <select
                value={teamFilter}
                onChange={(e) => setTeamFilter(e.target.value)}
                className="px-3 py-2.5 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl text-slate-900 dark:text-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all duration-200"
              >
                <option value="">All teams</option>
                <option value="Research">Research</option>
                <option value="Engineer">Engineer</option>
                <option value="Event">Event</option>
                <option value="Media">Media</option>
              </select>

              {/* Type Filter */}
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="px-3 py-2.5 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl text-slate-900 dark:text-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all duration-200"
              >
                <option value="">All types</option>
                <option value="CLC">CLC</option>
                <option value="DT">DT</option>
                <option value="TN">TN</option>
              </select>

              {/* Role Filter */}
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                className="px-3 py-2.5 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl text-slate-900 dark:text-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all duration-200"
              >
                <option value="">All roles</option>
                <option value="ROLE_ADMIN">Admin</option>
                <option value="ROLE_MANAGER">Manager</option>
                <option value="ROLE_USER">User</option>
                <option value="ROLE_ALUMNI">Alumni</option>
              </select>

              {/* Bulk Upload */}
              <input
                id="user-file-input"
                type="file"
                accept=".csv,.xlsx,.xls"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFilePicked(f);
                }}
              />
              <button
                onClick={() => document.getElementById("user-file-input")?.click()}
                className="px-4 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium transition-all duration-200 active:scale-95"
              >
                Bulk upload
              </button>

              {/* Refresh */}
              <button
                onClick={load}
                className="px-4 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium transition-all duration-200 active:scale-95"
              >
                Refresh
              </button>
            </div>
          </div>
        </div>

        {/* Pending Users (admin only) */}
        <PendingUsersSection isAdmin={isAdmin} onApproved={load} />

        {/* Table Header */}
        <div className="bg-white dark:bg-slate-900 rounded-t-xl border border-b-0 border-slate-200 dark:border-slate-800 overflow-x-auto">
          <div className="grid grid-cols-12 gap-2 sm:gap-4 items-center px-4 sm:px-6 py-3 text-xs sm:text-sm font-semibold text-slate-700 dark:text-slate-300 min-w-max sm:min-w-full">
            <button
              onClick={() => toggleSort("name")}
              className="col-span-5 text-left flex items-center gap-2 hover:text-slate-900 dark:hover:text-slate-100 transition-colors duration-200"
            >
              <span>Username</span>
              {sortKey === "name" && (
                <span className="text-xs text-blue-600 dark:text-blue-400">
                  {sortDir === "asc" ? "▲" : "▼"}
                </span>
              )}
            </button>
            <button
              onClick={() => toggleSort("role")}
              className="col-span-1 text-center hover:text-slate-900 dark:hover:text-slate-100 transition-colors duration-200"
            >
              Role {sortKey === "role" && (sortDir === "asc" ? "▲" : "▼")}
            </button>
            <button
              onClick={() => toggleSort("team")}
              className="col-span-1 text-center hover:text-slate-900 dark:hover:text-slate-100 transition-colors duration-200"
            >
              Team {sortKey === "team" && (sortDir === "asc" ? "▲" : "▼")}
            </button>
            <button
              onClick={() => toggleSort("score")}
              className="col-span-1 text-center hover:text-slate-900 dark:hover:text-slate-100 transition-colors duration-200"
            >
              Score {sortKey === "score" && (sortDir === "asc" ? "▲" : "▼")}
            </button>
            <button
              onClick={() => toggleSort("dateAdded")}
              className="col-span-2 text-center hover:text-slate-900 dark:hover:text-slate-100 transition-colors duration-200"
            >
              Date added {sortKey === "dateAdded" && (sortDir === "asc" ? "▲" : "▼")}
            </button>
            <button
              onClick={() => toggleSort("status")}
              className="col-span-2 text-center hover:text-slate-900 dark:hover:text-slate-100 transition-colors duration-200"
            >
              Status {sortKey === "status" && (sortDir === "asc" ? "▲" : "▼")}
            </button>
          </div>
        </div>

        {/* List */}
        <div className="space-y-2 rounded-b-xl bg-white dark:bg-slate-900 border border-t-0 border-slate-200 dark:border-slate-800 p-2">
          {loading && (
            <div className="py-12 px-4 text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <p className="mt-4 text-slate-600 dark:text-slate-400 font-medium">Loading users...</p>
            </div>
          )}
          {!loading && filteredAndSorted.length > 0 && filteredAndSorted.map((u) => (
            <UserRow key={u.id} user={u} onClick={(user) => setDetail(user)} onToggleStatus={toggleStatusLocal} isAdmin={isAdmin} />
          ))}
          {!loading && filteredAndSorted.length === 0 && (
            <div className="py-12 px-4 text-center">
              <p className="text-slate-500 dark:text-slate-400 font-medium">No users found</p>
            </div>
          )}
        </div>
      </div>

      <DetailModal user={detail} onClose={() => setDetail(null)} isAdmin={isAdmin} onUserUpdated={load} />
    </div>
  );
}
