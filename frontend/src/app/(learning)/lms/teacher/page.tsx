"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import lmsService from "@/services/lmsService";
import { Button } from "@/components/ui/button";

interface Course {
  id: number;
  title: string;
  description: string;
  status: string;
  level: string;
  category: string;
  created_at: string;
}

export default function TeacherDashboardPage() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const data = await lmsService.listMyCourses({ page_size: 100 });
      setCourses(data?.data || []);
      setError("");
    } catch (err) {
      console.error("Error loading dashboard:", err);
      setError("Không thể tải dữ liệu dashboard");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[600px]">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Đang tải dashboard...</p>
        </div>
      </div>
    );
  }

  const totalCourses = courses.length;
  const publishedCourses = courses.filter(c => c.status === "PUBLISHED").length;
  const draftCourses = courses.filter(c => c.status === "DRAFT").length;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Dashboard Giảng viên</h1>
        <p className="text-gray-600 mt-2">Xin chào! Đây là bảng điều khiển của bạn</p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-sm text-gray-600 mb-2">Tổng khóa học</h3>
          <p className="text-3xl font-bold text-blue-600">{totalCourses}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-sm text-gray-600 mb-2">Đã xuất bản</h3>
          <p className="text-3xl font-bold text-green-600">{publishedCourses}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-sm text-gray-600 mb-2">Bản nháp</h3>
          <p className="text-3xl font-bold text-orange-600">{draftCourses}</p>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-gray-900">Thao tác nhanh</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Button
            onClick={() => router.push("/lms/teacher/courses/create")}
            className="p-6 bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-lg hover:from-blue-600 hover:to-blue-700 transition-all"
          >
            <div className="text-center">
              <p className="text-lg font-semibold mb-1">Tạo khóa học mới</p>
              <p className="text-sm opacity-90">Bắt đầu tạo khóa học của bạn</p>
            </div>
          </Button>
          <Button
            onClick={() => router.push("/lms/teacher/courses")}
            className="p-6 bg-gradient-to-r from-purple-500 to-purple-600 text-white rounded-lg hover:from-purple-600 hover:to-purple-700 transition-all"
          >
            <div className="text-center">
              <p className="text-lg font-semibold mb-1">Quản lý khóa học</p>
              <p className="text-sm opacity-90">Xem và chỉnh sửa khóa học</p>
            </div>
          </Button>
          <Button
            onClick={loadDashboard}
            className="p-6 bg-gradient-to-r from-gray-500 to-gray-600 text-white rounded-lg hover:from-gray-600 hover:to-gray-700 transition-all"
          >
            <div className="text-center">
              <p className="text-lg font-semibold mb-1">Làm mới</p>
              <p className="text-sm opacity-90">Cập nhật dữ liệu mới nhất</p>
            </div>
          </Button>
        </div>
      </div>

      {courses.length > 0 && (
        <div className="mt-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Khóa học gần đây</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {courses.slice(0, 6).map((course) => (
              <div
                key={course.id}
                onClick={() => router.push(`/lms/teacher/courses/${course.id}`)}
                className="bg-white rounded-lg shadow-sm border p-4 hover:shadow-md transition-shadow cursor-pointer"
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-gray-800 line-clamp-2">{course.title}</h3>
                  <span className={`px-2 py-1 rounded text-xs font-medium whitespace-nowrap ml-2 ${
                    course.status === "PUBLISHED" 
                      ? "bg-green-100 text-green-800"
                      : "bg-yellow-100 text-yellow-800"
                  }`}>
                    {course.status === "PUBLISHED" ? "Xuất bản" : "Nháp"}
                  </span>
                </div>
                <p className="text-sm text-gray-600 line-clamp-2 mb-2">
                  {course.description || "Chưa có mô tả"}
                </p>
                <div className="flex gap-2 text-xs text-gray-500">
                  {course.category && (
                    <span className="bg-gray-100 px-2 py-1 rounded">{course.category}</span>
                  )}
                  {course.level && (
                    <span className="bg-gray-100 px-2 py-1 rounded">{course.level}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}