"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCookie } from "@/utils/cookies";
import { StatCard } from "@/components/lms/admin/StatCard";
import { ActionCard } from "@/components/lms/admin/ActionCard";
import { PendingEnrollmentItem } from "@/components/lms/admin/PendingEnrollmentItem";
import { ProgressBar } from "@/components/lms/admin/ProgressBar";

interface DashboardStats {
  totalCourses: number;
  publishedCourses: number;
  draftCourses: number;
  totalEnrollments: number;
  pendingEnrollments: number;
  totalStudents: number;
  totalTeachers: number;
  activeStudents: number;
}

export default function AdminDashboard() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [stats, setStats] = useState<DashboardStats>({
    totalCourses: 0,
    publishedCourses: 0,
    draftCourses: 0,
    totalEnrollments: 0,
    pendingEnrollments: 0,
    totalStudents: 0,
    totalTeachers: 0,
    activeStudents: 0,
  });
  const [userName, setUserName] = useState("");

  useEffect(() => {
    const selectedRole = sessionStorage.getItem("lms_selected_role");
    
    if (selectedRole !== "ADMIN") {
      router.push("/lms");
      return;
    }

    const name = getCookie("userName") || "";
    setUserName(name);
    
    loadDashboardData();
  }, [router]);

  const loadDashboardData = async () => {
    try {
      // Load stats from API
      // const data = await lmsService.getAdminStats();
      // setStats(data);
      
      // Mock data for now
      setStats({
        totalCourses: 12,
        publishedCourses: 8,
        draftCourses: 4,
        totalEnrollments: 156,
        pendingEnrollments: 8,
        totalStudents: 45,
        totalTeachers: 12,
        activeStudents: 38,
      });
      
      setLoading(false);
    } catch (error) {
      console.error("Error loading stats:", error);
      setLoading(false);
    }
  };

  const handleSyncUsers = async () => {
    try {
      setSyncing(true);
      const token = getCookie("authToken");
      
      const response = await fetch("http://localhost:8081/api/v1/admin/sync-users", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const data = await response.json();
        alert(`✅ Đã đồng bộ ${data.synced_count} người dùng thành công!`);
        await loadDashboardData();
      } else {
        const error = await response.json();
        alert(`❌ Đồng bộ thất bại: ${error.error || "Unknown error"}`);
      }
    } catch (error) {
      console.error(error);
      alert("❌ Có lỗi xảy ra khi đồng bộ người dùng");
    } finally {
      setSyncing(false);
    }
  };

  const handleChangeRole = () => {
    sessionStorage.removeItem("lms_selected_role");
    router.push("/lms");
  };

  const handleBackToHome = () => {
    router.push("/");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-purple-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Đang tải dữ liệu...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-transparent">
      {/* Header */}
      <header className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                <span className="text-3xl">👑</span>
                <div>
                  <h1 className="text-2xl font-bold text-gray-800">Quản trị LMS</h1>
                  <p className="text-sm text-gray-500">Xin chào, {userName}</p>
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <button
                onClick={handleBackToHome}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border rounded-lg hover:bg-gray-50 transition-colors"
              >
                🏠 Trang chủ
              </button>
              <button
                onClick={handleChangeRole}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border rounded-lg hover:bg-gray-50 transition-colors"
              >
                🔄 Đổi vai trò
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            icon="📚"
            title="Tổng khóa học"
            value={stats.totalCourses}
            subtitle={`${stats.publishedCourses} đã xuất bản, ${stats.draftCourses} nháp`}
            color="blue"
          />
          <StatCard
            icon="👥"
            title="Tổng đăng ký"
            value={stats.totalEnrollments}
            subtitle={`${stats.pendingEnrollments} chờ duyệt`}
            color="green"
            trend={stats.pendingEnrollments > 0 ? "warning" : undefined}
          />
          <StatCard
            icon="🎓"
            title="Học viên"
            value={stats.totalStudents}
            subtitle={`${stats.activeStudents} đang hoạt động`}
            color="purple"
          />
          <StatCard
            icon="👨‍🏫"
            title="Giảng viên"
            value={stats.totalTeachers}
            subtitle="Đang hoạt động"
            color="orange"
          />
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-xl shadow-sm border p-6 mb-8">
          <h2 className="text-xl font-bold text-gray-800 mb-6 flex items-center gap-2">
            <span>⚡</span>
            <span>Thao tác nhanh</span>
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <ActionCard
              icon="🔄"
              title="Đồng bộ người dùng"
              description="Đồng bộ từ Auth Service"
              onClick={handleSyncUsers}
              loading={syncing}
              variant="primary"
            />
            <ActionCard
              icon="➕"
              title="Thêm khóa học"
              description="Tạo khóa học mới"
              onClick={() => router.push("/lms/admin/courses/create")}
              variant="success"
            />
            <ActionCard
              icon="✅"
              title="Duyệt đăng ký"
              description={`${stats.pendingEnrollments} chờ duyệt`}
              onClick={() => router.push("/lms/admin/enrollments")}
              badge={stats.pendingEnrollments}
              variant="warning"
            />
            <ActionCard
              icon="📊"
              title="Báo cáo"
              description="Xem thống kê chi tiết"
              onClick={() => router.push("/lms/admin/analytics")}
              variant="info"
            />
            <ActionCard
              icon="👥"
              title="Quản lý người dùng"
              description="Phân quyền và quản lý"
              onClick={() => router.push("/lms/admin/users")}
              variant="default"
            />
            <ActionCard
              icon="⚙️"
              title="Cài đặt hệ thống"
              description="Cấu hình LMS"
              onClick={() => router.push("/lms/admin/settings")}
              variant="default"
            />
          </div>
        </div>

        {/* Recent Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Pending Enrollments */}
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                <span>📋</span>
                <span>Đăng ký chờ duyệt</span>
              </h3>
              {stats.pendingEnrollments > 0 && (
                <span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-semibold rounded-full">
                  {stats.pendingEnrollments} mới
                </span>
              )}
            </div>
            
            {stats.pendingEnrollments > 0 ? (
              <div className="space-y-3">
                {/* Mock data - replace with real API */}
                <PendingEnrollmentItem 
                  studentName="Nguyễn Văn A"
                  courseName="Lập trình Python cơ bản"
                  time="2 giờ trước"
                />
                <PendingEnrollmentItem 
                  studentName="Trần Thị B"
                  courseName="Machine Learning nâng cao"
                  time="5 giờ trước"
                />
                <button
                  onClick={() => router.push("/lms/admin/enrollments")}
                  className="w-full py-2 text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  Xem tất cả →
                </button>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <div className="text-4xl mb-2">✅</div>
                <p className="text-sm">Không có đăng ký chờ duyệt</p>
              </div>
            )}
          </div>

          {/* System Overview */}
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
              <span>📈</span>
              <span>Tổng quan hệ thống</span>
            </h3>
            
            <div className="space-y-4">
              <ProgressBar
                label="Khóa học đã xuất bản"
                value={stats.publishedCourses}
                max={stats.totalCourses}
                color="blue"
              />
              <ProgressBar
                label="Học viên hoạt động"
                value={stats.activeStudents}
                max={stats.totalStudents}
                color="green"
              />
              <ProgressBar
                label="Tỷ lệ hoàn thành đăng ký"
                value={stats.totalEnrollments - stats.pendingEnrollments}
                max={stats.totalEnrollments}
                color="purple"
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}