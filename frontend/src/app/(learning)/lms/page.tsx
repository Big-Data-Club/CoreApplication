"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCookie } from "@/utils/cookies";
import { Button } from "@/components/ui/button";
import lmsService from "@/services/lmsService";

interface RoleOption {
  value: string;
  label: string;
  description: string;
  icon: string;
  color: string;
  gradient: string;
}

const ROLE_OPTIONS: Record<string, RoleOption> = {
  ADMIN: {
    value: "admin",
    label: "Quản trị viên",
    description: "Quản lý toàn bộ hệ thống LMS, người dùng và khóa học",
    icon: "👑",
    color: "from-purple-500 to-pink-500",
    gradient: "bg-gradient-to-br from-purple-50 to-pink-50",
  },
  TEACHER: {
    value: "teacher",
    label: "Giảng viên",
    description: "Tạo và quản lý khóa học, bài giảng, đánh giá học viên",
    icon: "📚",
    color: "from-blue-500 to-cyan-500",
    gradient: "bg-gradient-to-br from-blue-50 to-cyan-50",
  },
  STUDENT: {
    value: "student",
    label: "Học viên",
    description: "Học tập, làm bài tập và theo dõi tiến độ học tập",
    icon: "🎓",
    color: "from-green-500 to-emerald-500",
    gradient: "bg-gradient-to-br from-green-50 to-emerald-50",
  },
};

export default function LMSRoleSelection() {
  const router = useRouter();
  const [userRoles, setUserRoles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userName, setUserName] = useState("");

  useEffect(() => {
    fetchUserRoles();
  }, []);

  const fetchUserRoles = async () => {
    try {
      const token = getCookie("authToken");

      // Get user info from token or API
      const userNameCookie = getCookie("userName") || "";
      setUserName(userNameCookie);

      const data = await lmsService.getMyRoles();
      console.log(data)
      const roles = data || [];

      if (roles.length === 0) {
        setError("Bạn chưa được cấp quyền sử dụng LMS. Vui lòng liên hệ quản trị viên.");
        setLoading(false);
        return;
      }

      // If user has only one role, auto-redirect
      if (roles.length === 1) {
        selectRole(roles[0]);
        return;
      }

      setUserRoles(roles);
      setLoading(false);
    } catch (err) {
      console.error("Error fetching roles:", err);
      setError(err instanceof Error ? err.message : "Đã xảy ra lỗi khi tải vai trò");
      setLoading(false);
    }
  };

  const selectRole = (role: string) => {
    sessionStorage.setItem("lms_selected_role", role);
    sessionStorage.setItem("lms_role_selected_at", new Date().toISOString());
    router.push(`/lms/${role.toLowerCase()}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-700 text-lg">Đang tải vai trò của bạn...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-transparent">
        <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8 text-center">
          <div className="text-6xl mb-4">⚠️</div>
          <h2 className="text-2xl font-bold text-gray-800 mb-3">Không có quyền truy cập</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <div className="flex gap-3 justify-center">
            <Button
              onClick={() => router.push("/")}
              className="px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Quay lại trang chủ
            </Button>
            <Button
              onClick={() => router.push("/contact")}
              className="px-6 py-2.5 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors font-medium"
            >
              Liên hệ hỗ trợ
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-transparent flex items-center justify-center p-4">
      <div className="max-w-6xl w-full">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-white rounded-full shadow-lg mb-4">
            <span className="text-4xl">🎓</span>
          </div>
          <h1 className="text-4xl font-bold text-gray-800 mb-3">
            Chào mừng đến với LMS
          </h1>
          {userName && (
            <p className="text-xl text-gray-600 mb-2">
              Xin chào, <span className="font-semibold text-gray-800">{userName}</span>!
            </p>
          )}
          <p className="text-gray-600 text-lg">
            Bạn có <span className="font-semibold text-blue-600">{userRoles.length}</span> vai trò trong hệ thống. 
            Vui lòng chọn vai trò bạn muốn sử dụng.
          </p>
        </div>

        {/* Role Cards */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {userRoles.map((role) => {
            const option = ROLE_OPTIONS[role];
            if (!option) return null;

            return (
              <Button
                key={role}
                onClick={() => selectRole(role)}
                className={`${option.gradient} rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 transform hover:scale-105 p-8 text-center group relative overflow-hidden`}
              >
                {/* Animated background */}
                <div className={`absolute inset-0 bg-gradient-to-br ${option.color} opacity-0 group-hover:opacity-10 transition-opacity duration-300`}></div>
                
                {/* Content */}
                <div className="relative z-10">
                  <div className="text-6xl mb-4 group-hover:scale-110 transition-transform duration-300">
                    {option.icon}
                  </div>
                  <h3 className="text-2xl font-bold text-gray-800 mb-2">
                    {option.label}
                  </h3>
                  <p className="text-gray-600 text-sm mb-6 min-h-[3rem]">
                    {option.description}
                  </p>
                  <div className={`bg-gradient-to-r ${option.color} text-white py-2.5 px-6 rounded-lg transition-all group-hover:shadow-lg inline-flex items-center gap-2 font-medium`}>
                    <span>Chọn vai trò</span>
                    <span className="group-hover:translate-x-1 transition-transform">→</span>
                  </div>
                </div>
              </Button>
            );
          })}
        </div>

        {/* Footer Actions */}
        <div className="text-center space-y-3">
          <Button
            onClick={() => router.push("/")}
            className="text-gray-600 hover:text-gray-800 font-medium underline underline-offset-4 transition-colors"
          >
            ← Quay lại trang chủ
          </Button>
          <div className="text-sm text-gray-500">
            Bạn có thể thay đổi vai trò bất cứ lúc nào từ menu trong dashboard
          </div>
        </div>
      </div>
    </div>
  );
}