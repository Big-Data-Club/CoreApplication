"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { GoogleOAuthProvider, GoogleLogin } from "@react-oauth/google";
import { signIn } from "next-auth/react";
import { Spinner } from "@/components/icons/Icons";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

interface GoogleLoginButtonProps {
  onError: (msg: string) => void;
}

export function GoogleLoginButton({ onError }: GoogleLoginButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const handleGoogleSuccess = async (credentialResponse: any) => {
    const idToken = credentialResponse.credential;
    if (!idToken) {
      onError("Không nhận được token từ Google.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/apiv1/api/auth/google/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idToken }),
      });

      const data = await res.json();

      if (res.status === 404) {
        // User doesn't exist — redirect to registration with Google profile
        sessionStorage.setItem("googleProfile", JSON.stringify({
          ...data,
          idToken,
        }));
        router.push("/register/google");
        return;
      }

      if (res.status === 403) {
        const msg = data.error === "PENDING_APPROVAL"
          ? "Tài khoản đang chờ admin duyệt."
          : "Tài khoản đã bị khóa. Liên hệ admin.";
        onError(msg);
        return;
      }

      if (!res.ok) {
        onError(data.message || "Đăng nhập Google thất bại.");
        return;
      }

      // Extract tokens from cookies if available
      const setCookie = res.headers.get("set-cookie");
      const authTokenMatch = setCookie?.match(/authToken=([^;]+)/);
      const refreshTokenMatch = setCookie?.match(/refreshToken=([^;]+)/);

      // Sign in with NextAuth using the backend-verified credentials
      const result = await signIn("google-backend", {
        redirect: false,
        userId: String(data.userId),
        name: data.name,
        email: data.email,
        role: data.role,
        token: authTokenMatch?.[1] || data.token,
        refreshToken: refreshTokenMatch?.[1] || "",
        expiresIn: String(data.expiresIn),
      });

      if (result?.error) {
        onError("Đăng nhập thất bại. Vui lòng thử lại.");
        return;
      }

      router.push("/dashboard");
      router.refresh();
    } catch (err: any) {
      onError(err.message || "Đăng nhập Google thất bại.");
    } finally {
      setLoading(false);
    }
  };

  if (!GOOGLE_CLIENT_ID) {
    return null;
  }

  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <div className="flex flex-col items-center">
        {loading ? (
          <div className="flex items-center justify-center py-3">
            <Spinner />
            <span className="ml-2 text-sm text-slate-500">Đang xử lý...</span>
          </div>
        ) : (
          <div className="w-full flex justify-center">
            <GoogleLogin
              onSuccess={handleGoogleSuccess}
              onError={() => onError("Đăng nhập Google thất bại.")}
              theme="outline"
              size="large"
              width="350"
              text="signin_with"
              shape="rectangular"
              logo_alignment="left"
            />
          </div>
        )}
      </div>
    </GoogleOAuthProvider>
  );
}
