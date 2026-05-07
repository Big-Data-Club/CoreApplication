"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { EyeIcon, EyeOffIcon, Spinner } from "@/components/icons/Icons";
import { validatePassword } from "@/utils/utils";
import ForgotPasswordModal from "./ForgotPasswordModal";
import Mascot from "./Mascot";
import { GoogleLoginButton } from "./GoogleLoginButton";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [isPasswordFocused, setIsPasswordFocused] = useState(false);
  const [isForgotOpen, setIsForgotOpen] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const v = validatePassword(email, password);
    if (v) return setError(v);

    setLoading(true);
    try {
      const result = await (await import("next-auth/react")).signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (result?.error) {
        throw new Error("Email hoặc mật khẩu không chính xác.");
      }

      router.push("/dashboard");
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Đăng nhập thất bại. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <ForgotPasswordModal open={isForgotOpen} onClose={() => setIsForgotOpen(false)} />

      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-sm p-8 mx-auto">
        <Mascot isBlindfolded={isPasswordFocused && !showPassword} />

        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-900">Chào mừng trở lại!</h1>
          <p className="text-sm text-slate-500 mt-2">Đăng nhập vào hệ thống quản trị BDC</p>
        </div>

        {error && (
          <div className="mb-6 text-sm font-medium text-red-600 bg-red-50 border border-red-200 px-4 py-3 rounded-xl flex items-start gap-2">
            <span>⚠️</span> {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onFocus={() => setIsPasswordFocused(false)}
              placeholder="nguyenvana@hcmut.edu.vn"
              className="w-full border border-slate-300 rounded-xl p-3.5 text-slate-900 placeholder:text-slate-400 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
              required
            />
          </div>

          <div className="relative">
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">Mật khẩu</label>
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onFocus={() => setIsPasswordFocused(true)}
              onBlur={() => setIsPasswordFocused(false)}
              placeholder="••••••••"
              className="w-full border border-slate-300 rounded-xl p-3.5 pr-12 text-slate-900 placeholder:text-slate-400 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-4 top-[38px] text-slate-400 hover:text-slate-600 transition-colors focus:outline-none"
            >
              {showPassword ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </div>

          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 cursor-pointer group">
              <input type="checkbox" className="w-4 h-4 rounded border-slate-300 accent-blue-600 cursor-pointer" />
              <span className="text-slate-600 group-hover:text-slate-900 transition-colors">Ghi nhớ đăng nhập</span>
            </label>
            <button
              type="button"
              onClick={() => setIsForgotOpen(true)}
              className="font-semibold text-blue-600 hover:text-blue-700 transition-colors active:scale-95"
            >
              Quên mật khẩu?
            </button>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl px-6 py-3.5 shadow-sm transition-all active:scale-95 disabled:opacity-70 flex items-center justify-center gap-2"
          >
            {loading ? <Spinner /> : "Đăng nhập"}
          </button>
        </form>

        {/* Divider */}
        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-3 bg-white text-slate-400 font-medium">hoặc</span>
          </div>
        </div>

        {/* Google Login */}
        <GoogleLoginButton onError={setError} />
      </div>
    </>
  );
}