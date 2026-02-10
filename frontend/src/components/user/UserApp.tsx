/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";
import React, { useEffect, useMemo, useState } from "react";
import { User } from "@/types";
import { fetchUsers, postBulkRegister } from "@/lib/users/api";
import { parseFile } from "@/lib/users/fileParser";
import UserRow from "./UserRow";
import DetailModal from "./DetailModal";
import { mapFrontendRoleToBackend, mapFrontendTeamToBackend, mapFrontendTypeToBackend } from "@/lib/users/auth";

export default function UserApp() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

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

  function toggleStatusLocal(id: string | number) {
    setUsers((s) => s.map(u => (u.id === id ? { ...u, status: !u.status } : u)));
    // optionally persist to backend (PATCH /api/users/{id}) if API exists
  }

  const filteredAndSorted = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = users.filter(u => {
      if (teamFilter && u.team !== teamFilter) return false;
      if (typeFilter && u.type !== typeFilter) return false;
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
    <div className="bg-transparent min-h-screen bg-[#eef2ff] p-4 sm:p-6 lg:p-8">
      <div className="max-w-[1200px] mx-auto px-2 sm:px-0">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-6 mb-6">
          <div>
            <h1 className="text-3xl font-bold">Users</h1>
            <div className="text-sm text-gray-500">{users.length} Users</div>
            {error && <div className="text-sm text-red-500 mt-1">Error: {error}</div>}
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search anything ..." className="pl-10 pr-4 py-2 rounded-full w-80 border" />
            </div>

            <select value={teamFilter} onChange={(e) => setTeamFilter(e.target.value)} className="rounded border px-3 py-2">
              <option value="">All teams</option>
              <option value="Research">Research</option>
              <option value="Engineer">Engineer</option>
              <option value="Event">Event</option>
              <option value="Media">Media</option>
            </select>

            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="rounded border px-3 py-2">
              <option value="">All types</option>
              <option value="CLC">CLC</option>
              <option value="DT">DT</option>
              <option value="TN">TN</option>
            </select>

            <input id="user-file-input" type="file" accept=".csv,.xlsx,.xls" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFilePicked(f); }} />
            <button onClick={() => document.getElementById("user-file-input")?.click()} className="px-3 py-2 rounded border">Bulk upload</button>

            <button onClick={load} className="px-3 py-2 rounded border ml-2">Refresh</button>
          </div>
        </div>

        {/* table header */}
        <div className="bg-white rounded-t-lg shadow-sm overflow-x-auto">
          <div className="grid grid-cols-12 gap-2 sm:gap-4 items-center px-3 sm:px-6 py-3 text-xs sm:text-sm font-medium text-gray-600 min-w-max">
            <button onClick={() => toggleSort("name")} className="col-span-5 text-left flex items-center gap-2">
              <span>Username</span>
              <small className="text-xs text-gray-400">{sortKey === "name" ? (sortDir === "asc" ? "▲" : "▼") : null}</small>
            </button>
            <button onClick={() => toggleSort("role")} className="col-span-1 text-center">Role</button>
            <button onClick={() => toggleSort("team")} className="col-span-1 text-center">Team</button>
            <button onClick={() => toggleSort("score")} className="col-span-1 text-center">Scores</button>
            <button onClick={() => toggleSort("dateAdded")} className="col-span-2 text-center">Date added</button>
            <button onClick={() => toggleSort("status")} className="col-span-2 text-center">Status</button>
          </div>
        </div>

        {/* list */}
        <div className="space-y-3 mt-2">
          {loading && <div className="text-center py-8 bg-white rounded-lg shadow-sm">Loading users...</div>}
          {!loading && filteredAndSorted.map(u => (
            <UserRow key={u.id} user={u} onClick={(user)=>setDetail(user)} onToggleStatus={toggleStatusLocal} />
          ))}
          {!loading && filteredAndSorted.length === 0 && <div className="text-center text-gray-500 py-8 bg-white rounded-lg shadow-sm">No users found</div>}
        </div>
      </div>

      <DetailModal user={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
