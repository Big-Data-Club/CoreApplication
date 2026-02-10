/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { EyeIcon, EyeOffIcon, Spinner } from "@/components/icons/Icons";
import { useUser } from "@/store/UserContext";
import { userService } from "@/services/userService";
import { validatePassword } from "@/utils/utils";
import { Logo } from "@/components/layout/Logo";
import { Feature } from "@/components/layout/Feature";

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useUser();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const v = validatePassword(email, password);
    if (v) {
      setError(v);
      return;
    }
    setLoading(true);
    try {
      const { token, name, email: userEmail, role, userId, maxAge } = await userService.login(email,password)
      document.cookie = `authToken=${token}; path=/; max-age=${maxAge}; SameSite=Strict; ${process.env.NODE_ENV === 'production' ? '' : ''}`;
      setUser({ id:userId, name, email: userEmail, role });
      setSuccess("Đăng nhập thành công! Đang chuyển hướng...");
      setTimeout(() => {
        router.push("/");
      }, 500);
    } catch (err: any) {
      setError(err.message || "Đăng nhập thất bại. Vui lòng kiểm tra thông tin.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-transparent w-full h-screen from-[#eef2ff] to-[#f7f1ff] flex items-center justify-center p-4 sm:p-6">
      <div aria-hidden className="absolute inset-0 overflow-hidden -z-10">
        <div className="absolute -left-32 -top-32 w-64 h-64 sm:w-96 sm:h-96 bg-gradient-to-tr from-[#c7b3ff] to-[#88ccff] opacity-20 rounded-full blur-3xl transform rotate-12" />
        <div className="absolute -right-32 -bottom-32 w-56 h-56 sm:w-96 sm:h-96 bg-gradient-to-br from-[#ffd3d3] to-[#ffc8a2] opacity-18 rounded-full blur-3xl transform -rotate-12" />
      </div>

      <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8 items-center">
        <div className="hidden lg:flex flex-col justify-center gap-4 lg:gap-6 pl-4 lg:pl-6 pr-2 lg:pr-4">
          <div className="flex items-center gap-3">
            <Logo />
            <div>
              <h2 className="text-xl lg:text-2xl font-extrabold">Big Data Club</h2>
              <p className="text-xs lg:text-sm text-gray-500">Think Big • Speak Data</p>
            </div>
          </div>

          <h1 className="text-3xl lg:text-4xl font-bold leading-tight">Welcome back</h1>
          <p className="text-sm lg:text-base text-gray-600 max-w-md">
            Đăng nhập thuiiiiii
          </p>

          <div className="mt-4 lg:mt-6 space-y-3">
            <Feature title="BDCers" desc="Trang quản lý hoạt động dành riêng cho các thành viên BDC" />
            <Feature title="Top 1" desc="Câu lạc bộ top 1" />
          </div>

          <div className="mt-auto text-xs lg:text-sm text-gray-400">© {new Date().getFullYear()} Big Data Club</div>
        </div>

        <div className="bg-white/90 backdrop-blur-md rounded-xl sm:rounded-2xl shadow-lg p-5 sm:p-6 lg:p-8 w-full max-w-sm lg:max-w-none">
          <div className="mb-4 sm:mb-6">
            <h2 className="text-xl sm:text-2xl font-semibold">Sign in to your account</h2>
            <p className="text-xs sm:text-sm text-gray-500 mt-1">Nhập thông tin đăng nhập để tiếp tục</p>
          </div>

          <div className="min-h-6 mb-4">
            {error && (
              <div role="alert" className="mb-3 text-xs sm:text-sm text-red-700 bg-red-50 border border-red-100 px-3 py-2 rounded">
                {error}
              </div>
            )}
            {success && (
              <div role="status" className="mb-3 text-xs sm:text-sm text-green-800 bg-green-50 border border-green-100 px-3 py-2 rounded">
                {success}
              </div>
            )}
          </div>

          <form onSubmit={onSubmit} className="space-y-4 sm:space-y-5">
            <label className="block">
              <span className="text-xs sm:text-sm font-medium text-gray-700">Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="mt-1.5 block w-full rounded-lg border border-gray-200 px-3 sm:px-4 py-2 sm:py-2.5 text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-indigo-300"
                autoComplete="email"
                required
              />
            </label>

            <label className="block relative">
              <span className="text-xs sm:text-sm font-medium text-gray-700">Password</span>
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="mt-1.5 block w-full rounded-lg border border-gray-200 px-3 sm:px-4 py-2 sm:py-2.5 pr-10 text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-indigo-300"
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-2 sm:right-3 top-9 sm:top-10 text-gray-500 hover:text-gray-700 p-1"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? EyeOffIcon() : EyeIcon()}
              </button>
            </label>

            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-4 text-xs sm:text-sm">
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300"
                />
                <span className="text-gray-600">Remember me</span>
              </label>

              <a className="text-indigo-600 hover:underline text-xs sm:text-sm" href="#">
                Forgot password?
              </a>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 sm:py-3 text-sm sm:text-base text-white font-medium hover:bg-indigo-700 disabled:opacity-60 transition-colors"
            >
              {loading ? (
                <>
                  <Spinner />
                  <span className="hidden sm:inline">Signing in...</span>
                  <span className="sm:hidden">Đang đăng nhập...</span>
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}