"use client";

import { useState } from "react";
import { X, Mail, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { userService } from "@/services/userService";

interface ForgotPasswordModalProps {
  open: boolean;
  onClose: () => void;
}

type ModalState = "idle" | "loading" | "success" | "error";

export default function ForgotPasswordModal({ open, onClose }: ForgotPasswordModalProps) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<ModalState>("idle");
  const [errorText, setErrorText] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText("");
    setState("loading");

    try {
      await userService.forgotPassword(email);
      setState("success");
    } catch {
      // Generic error — don't expose backend details
      setState("error");
      setErrorText("Đã có lỗi xảy ra. Vui lòng thử lại sau.");
    }
  };

  const handleClose = () => {
    // Reset state when closing
    setEmail("");
    setState("idle");
    setErrorText("");
    onClose();
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      aria-modal="true"
      role="dialog"
      aria-labelledby="forgot-password-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Modal card */}
      <div className="relative z-10 w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl p-8 animate-in fade-in zoom-in-95 duration-200">
        {/* Close button */}
        <button
          type="button"
          onClick={handleClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-700 transition-colors active:scale-95"
          aria-label="Đóng"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Icon + Header */}
        <div className="text-center mb-7">
          <div className="w-14 h-14 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-4">
            <Mail className="w-7 h-7 text-blue-600" />
          </div>
          <h2 id="forgot-password-title" className="text-xl font-bold text-slate-900">
            Quên mật khẩu?
          </h2>
          <p className="text-sm text-slate-500 mt-2 leading-relaxed">
            Nhập email đăng ký của bạn. Chúng tôi sẽ gửi link đặt lại mật khẩu trong vài phút.
          </p>
        </div>

        {/* Success state */}
        {state === "success" && (
          <div className="flex flex-col items-center gap-4 py-2">
            <div className="flex items-start gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3.5 text-sm text-green-700 font-medium w-full">
              <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
              <p>
                Nếu email <strong>{email}</strong> tồn tại trong hệ thống, bạn sẽ nhận được
                link đặt lại mật khẩu trong vài phút. Vui lòng kiểm tra hộp thư (kể cả thư rác).
              </p>
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="w-full mt-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl px-6 py-3 shadow-sm transition-all active:scale-95"
            >
              Đã hiểu
            </button>
          </div>
        )}

        {/* Form state */}
        {state !== "success" && (
          <form onSubmit={handleSubmit} className="space-y-5">
            {state === "error" && (
              <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-600 font-medium">
                <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                <p>{errorText}</p>
              </div>
            )}

            <div>
              <label
                htmlFor="forgot-email"
                className="block text-sm font-semibold text-slate-700 mb-1.5"
              >
                Địa chỉ Email
              </label>
              <input
                id="forgot-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={state === "loading"}
                placeholder="nguyenvana@hcmut.edu.vn"
                className="w-full border border-slate-300 rounded-xl p-3.5 text-slate-900 placeholder:text-slate-400 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all disabled:opacity-60"
                required
                autoFocus
              />
            </div>

            <button
              type="submit"
              disabled={state === "loading"}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl px-6 py-3.5 shadow-sm transition-all active:scale-95 disabled:opacity-70 flex items-center justify-center gap-2"
            >
              {state === "loading" ? (
                <><Loader2 className="w-5 h-5 animate-spin" /> Đang gửi...</>
              ) : (
                "Gửi link đặt lại mật khẩu"
              )}
            </button>

            <button
              type="button"
              onClick={handleClose}
              className="w-full text-sm font-medium text-slate-500 hover:text-slate-700 transition-colors py-1"
            >
              Quay lại đăng nhập
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
