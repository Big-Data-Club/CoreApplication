"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/icons/Icons";

const TEAMS = [
  { value: "RESEARCH", label: "Research" },
  { value: "ENGINEER", label: "Engineer" },
  { value: "EVENT", label: "Event" },
  { value: "MEDIA", label: "Media" },
];

const TYPES = [
  { value: "CLC", label: "CLC" },
  { value: "TN", label: "TN" },
  { value: "DT", label: "ĐT" },
];

interface GoogleProfile {
  googleId: string;
  email: string;
  name: string;
  picture: string;
  idToken: string;
}

export function GoogleRegisterForm() {
  const router = useRouter();
  const [profile, setProfile] = useState<GoogleProfile | null>(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [team, setTeam] = useState("");
  const [type, setType] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem("googleProfile");
    if (!stored) {
      router.push("/login");
      return;
    }
    const parsed = JSON.parse(stored) as GoogleProfile;
    setProfile(parsed);
    setName(parsed.name || "");
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!code.trim()) return setError("Vui lòng nhập MSSV/Mã thành viên.");
    if (!team) return setError("Vui lòng chọn ban.");
    if (!type) return setError("Vui lòng chọn hệ đào tạo.");
    if (!profile) return;

    setLoading(true);
    try {
      const res = await fetch("/apiv1/api/auth/google/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idToken: profile.idToken,
          name: name.trim(),
          code: code.trim(),
          team,
          type,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.message || "Đăng ký thất bại. Vui lòng thử lại.");
        return;
      }

      // Clear stored profile
      sessionStorage.removeItem("googleProfile");
      router.push("/pending");
    } catch (err: any) {
      setError(err.message || "Đăng ký thất bại.");
    } finally {
      setLoading(false);
    }
  };

  if (!profile) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-sm p-8 mx-auto">
      {/* Google profile header */}
      <div className="text-center mb-6">
        {profile.picture && (
          <img
            src={profile.picture}
            alt={profile.name}
            className="w-20 h-20 rounded-full mx-auto mb-3 border-2 border-blue-100"
            referrerPolicy="no-referrer"
          />
        )}
        <h1 className="text-2xl font-bold text-slate-900">Hoàn tất đăng ký</h1>
        <p className="text-sm text-slate-500 mt-1">
          Bổ sung thông tin để tham gia Big Data Club
        </p>
      </div>

      {error && (
        <div className="mb-6 text-sm font-medium text-red-600 bg-red-50 border border-red-200 px-4 py-3 rounded-xl flex items-start gap-2">
          <span>⚠️</span> {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Email - readonly */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Email</label>
          <input
            type="email"
            value={profile.email}
            disabled
            className="w-full border border-slate-200 rounded-xl p-3.5 text-slate-500 bg-slate-100 cursor-not-allowed"
          />
        </div>

        {/* Name - editable */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Họ và tên</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nguyễn Văn A"
            className="w-full border border-slate-300 rounded-xl p-3.5 text-slate-900 placeholder:text-slate-400 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            required
          />
        </div>

        {/* Student code */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">
            MSSV / Mã thành viên
          </label>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="2212345"
            className="w-full border border-slate-300 rounded-xl p-3.5 text-slate-900 placeholder:text-slate-400 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            required
          />
        </div>

        {/* Team */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Ban</label>
          <select
            value={team}
            onChange={(e) => setTeam(e.target.value)}
            className="w-full border border-slate-300 rounded-xl p-3.5 text-slate-900 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            required
          >
            <option value="" disabled>Chọn ban</option>
            {TEAMS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        {/* Type */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Hệ đào tạo</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="w-full border border-slate-300 rounded-xl p-3.5 text-slate-900 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            required
          >
            <option value="" disabled>Chọn hệ</option>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full mt-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl px-6 py-3.5 shadow-sm transition-all active:scale-95 disabled:opacity-70 flex items-center justify-center gap-2"
        >
          {loading ? <Spinner /> : "Đăng ký"}
        </button>

        <p className="text-xs text-center text-slate-400 mt-3">
          Tài khoản sẽ cần được admin duyệt trước khi sử dụng.
        </p>
      </form>
    </div>
  );
}
