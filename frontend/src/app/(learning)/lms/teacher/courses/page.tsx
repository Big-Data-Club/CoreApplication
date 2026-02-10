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
  published_at?: string;
}

export default function CoursesListPage() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    loadCourses();
  }, [filter]);

  const loadCourses = async () => {
    try {
      setLoading(true);
      const params = filter !== "all" ? { status: filter.toUpperCase() } : {};
      const data = await lmsService.listMyCourses(params);
      setCourses(data?.data || []);
    } catch (error) {
      console.error("Error loading courses:", error);
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async (courseId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Bạn có chắc muốn xuất bản khóa học này?")) return;
    
    try {
      await lmsService.publishCourse(courseId);
      alert("Xuất bản khóa học thành công!");
      loadCourses();
    } catch (error: any) {
      alert(error.response?.data?.error || "Lỗi khi xuất bản khóa học");
      console.error(error);
    }
  };

  const handleDelete = async (courseId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Bạn có chắc muốn xóa khóa học này? Hành động này không thể hoàn tác!")) return;
    
    try {
      await lmsService.deleteCourse(courseId);
      alert("Xóa khóa học thành công!");
      loadCourses();
    } catch (error: any) {
      alert(error.response?.data?.error || "Lỗi khi xóa khóa học");
      console.error(error);
    }
  };

  const filteredCourses = courses.filter(course =>
    course.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (course.description && course.description.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Đang tải khóa học...</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Khóa học của tôi</h1>
            <p className="text-gray-600 mt-1">Quản lý và tạo khóa học mới</p>
          </div>
          <Button
            onClick={() => router.push("/lms/teacher/courses/create")}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
          >
            Tạo khóa học mới
          </Button>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="relative">
            <input
              type="text"
              placeholder="Tìm kiếm khóa học..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="flex gap-2">
            {["all", "draft", "published"].map((status) => (
              <Button
                key={status}
                onClick={() => setFilter(status)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === status
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {status === "all" ? "Tất cả" : 
                 status === "draft" ? "Nháp" : "Xuất bản"}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t">
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-600">{courses.length}</p>
            <p className="text-sm text-gray-600">Tổng khóa học</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-green-600">
              {courses.filter(c => c.status === "PUBLISHED").length}
            </p>
            <p className="text-sm text-gray-600">Đã xuất bản</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-orange-600">
              {courses.filter(c => c.status === "DRAFT").length}
            </p>
            <p className="text-sm text-gray-600">Nháp</p>
          </div>
        </div>
      </div>

      {filteredCourses.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <h3 className="text-xl font-bold text-gray-800 mb-2">
            {searchTerm ? "Không tìm thấy khóa học" : "Chưa có khóa học nào"}
          </h3>
          <p className="text-gray-600 mb-6">
            {searchTerm 
              ? "Hãy thử tìm kiếm với từ khóa khác" 
              : "Bắt đầu tạo khóa học đầu tiên của bạn"}
          </p>
          {!searchTerm && (
            <Button
              onClick={() => router.push("/lms/teacher/courses/create")}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Tạo khóa học mới
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredCourses.map((course) => (
            <div
              key={course.id}
              className="bg-white rounded-xl shadow-sm border overflow-hidden hover:shadow-md transition-shadow"
            >
              <div
                onClick={() => router.push(`/lms/teacher/courses/${course.id}`)}
                className="p-6 cursor-pointer"
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="font-bold text-lg text-gray-800 line-clamp-2 flex-1">
                    {course.title}
                  </h3>
                  <span className={`px-3 py-1 rounded-full text-xs font-semibold ml-2 whitespace-nowrap ${
                    course.status === "PUBLISHED" 
                      ? "bg-green-100 text-green-800"
                      : "bg-yellow-100 text-yellow-800"
                  }`}>
                    {course.status === "PUBLISHED" ? "Xuất bản" : "Nháp"}
                  </span>
                </div>
                <p className="text-sm text-gray-600 line-clamp-3 mb-4">
                  {course.description || "Chưa có mô tả"}
                </p>
                <div className="flex gap-2 flex-wrap mb-4">
                  {course.category && (
                    <span className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">
                      {course.category}
                    </span>
                  )}
                  {course.level && (
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
                      {course.level}
                    </span>
                  )}
                </div>
              </div>
              
              <div className="px-6 py-3 bg-gray-50 border-t flex gap-2">
                <Button
                  onClick={() => router.push(`/lms/teacher/courses/${course.id}`)}
                  className="flex-1 px-3 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                >
                  Xem chi tiết
                </Button>
                {course.status === "DRAFT" && (
                  <Button
                    onClick={(e) => handlePublish(course.id, e)}
                    className="px-3 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700 transition-colors"
                  >
                    Xuất bản
                  </Button>
                )}
                <Button
                  onClick={(e) => handleDelete(course.id, e)}
                  className="px-3 py-2 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors"
                >
                  Xóa
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}