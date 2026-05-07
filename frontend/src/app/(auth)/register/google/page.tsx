import React from "react";
import { GoogleRegisterForm } from "@/components/login/GoogleRegisterForm";
import { Logo } from "@/components/layout/Logo";

export default function GoogleRegisterPage() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md mb-8 flex flex-row items-center justify-center gap-4">
        <Logo />
        <div className="flex flex-col items-start">
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">
            Big Data Club
          </h2>
          <p className="mt-1 text-sm font-semibold text-blue-600 uppercase tracking-widest">
            Think Big • Speak Data
          </p>
        </div>
      </div>

      <GoogleRegisterForm />
    </div>
  );
}
