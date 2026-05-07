"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Logo } from "@/components/layout/Logo";
import InvalidTokenCard from "@/components/login/InvalidTokenCard";
import ConfirmPasswordForm from "@/components/login/ConfirmPasswordForm";

function PasswordChangeContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const type = searchParams.get("type") as "change" | "reset" | null;

  if (!token) {
    return <InvalidTokenCard />;
  }

  return <ConfirmPasswordForm token={token} type={type ?? "change"} />;
}

export default function ConfirmPasswordChangePage() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md mb-8 flex flex-col items-center">
        <Logo />
        <h2 className="mt-4 text-center text-3xl font-extrabold text-slate-900 tracking-tight">
          Big Data Club
        </h2>
        <p className="mt-2 text-center text-sm font-semibold text-blue-600 uppercase tracking-widest">
          Account Security
        </p>
      </div>

      <Suspense fallback={<div className="text-center text-slate-500">Đang tải dữ liệu...</div>}>
        <PasswordChangeContent />
      </Suspense>

      <p className="text-center mt-10 text-sm text-slate-400 font-medium">
        © {new Date().getFullYear()} BDC Platform. All rights reserved.
      </p>
    </div>
  );
}
