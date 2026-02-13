/* eslint-disable @next/next/no-img-element */

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCookie } from "@/utils/cookies";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { lmsService } from "@/services/lmsService";
import { CheckCircle2, Clock, Loader } from "lucide-react";
import { Course, Enrollment, TabType } from "@/types";

export default function StudentDashboard() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [userName, setUserName] = useState("");
  const [activeTab, setActiveTab] = useState<TabType>('discover');
  const [courses, setCourses] = useState<Course[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [enrolling, setEnrolling] = useState<number | null>(null);
  const [cancelingId, setCancelingId] = useState<number | null>(null);

  useEffect(() => {
    const selectedRole = sessionStorage.getItem("lms_selected_role");
    if (selectedRole !== "STUDENT") {
      router.push("/lms");
      return;
    }

    const name = getCookie("userName") || "";
    setUserName(name);
    
    loadStudentData();
  }, [router]);

  const loadStudentData = async () => {
    try {
      // Load initial discover courses
      setLoading(true);
      const data = await lmsService.listPublishedCourses({ page_size: 20 });
      setCourses(data || []);
      setLoading(false);
    } catch (error) {
      console.error("Error loading student data:", error);
      setLoading(false);
    }
  };

  // Tab handlers
  const loadPublishedCourses = async () => {
    try {
      setLoading(true);
      const data = await lmsService.listPublishedCourses({ page_size: 20 });
      setCourses(data || []);
    } catch (error) {
      console.error("Failed to load courses:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadMyCourses = async () => {
    try {
      setLoading(true);
      const data = await lmsService.getMyEnrollments('ACCEPTED');
      setEnrollments(data || []);
    } catch (error) {
      console.error("Failed to load my courses:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadPendingEnrollments = async () => {
    try {
      setLoading(true);
      const data = await lmsService.getMyEnrollments('WAITING');
      setEnrollments(data || []);
    } catch (error) {
      console.error("Failed to load pending enrollments:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'discover') {
      loadPublishedCourses();
    } else if (activeTab === 'my-courses') {
      loadMyCourses();
    } else if (activeTab === 'pending') {
      loadPendingEnrollments();
    }
  }, [activeTab]);

  const handleEnroll = async (courseId: number) => {
    try {
      setEnrolling(courseId);
      await lmsService.enrollCourse(courseId);
      alert('Đã gửi yêu cầu đăng ký. Vui lòng chờ giáo viên xác nhận.');
      loadPublishedCourses();
    } catch (error: any) {
      alert(error.response?.data?.message || 'Lỗi khi đăng ký khóa học');
    } finally {
      setEnrolling(null);
    }
  };

  const handleCancelEnrollment = async (enrollmentId: number) => {
    if (!confirm('Bạn chắc chắn muốn hủy yêu cầu đăng ký này?')) return;

    try {
      setCancelingId(enrollmentId);
      await lmsService.cancelEnrollment(enrollmentId);
      alert('Yêu cầu đã bị hủy');
      loadPendingEnrollments();
    } catch (error: any) {
      alert(error.response?.data?.message || 'Lỗi khi hủy yêu cầu');
    } finally {
      setCancelingId(null);
    }
  };

  const handleChangeRole = () => {
    sessionStorage.removeItem("lms_selected_role");
    router.push("/lms");
  };

  const handleBackToHome = () => {
    router.push("/");
  };

  const renderDiscoverTab = () => (
    <div className="space-y-4">
      {loading ? (
        <div className="flex justify-center py-8">
          <Loader className="animate-spin w-8 h-8" />
        </div>
      ) : courses.length === 0 ? (
        <Card className="p-8 text-center text-gray-500">
          Không có khóa học nào để khám phá
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {courses.map((course) => (
            <Card key={course.id} className="overflow-hidden hover:shadow-lg transition-shadow">
              {course.thumbnail_url && (
                <img 
                  src={course.thumbnail_url} 
                  alt={course.title}
                  className="w-full h-40 object-cover"
                />
              )}
              <div className="p-4">
                <h3 className="font-semibold text-lg mb-2 line-clamp-2">{course.title}</h3>
                {course.teacher_name && (
                  <p className="text-sm text-gray-600 mb-2">Giáo viên: {course.teacher_name}</p>
                )}
                <p className="text-sm text-gray-700 mb-3 line-clamp-2">{course.description}</p>
                <div className="flex gap-2 flex-wrap mb-3">
                  {course.category && (
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                      {course.category}
                    </span>
                  )}
                  {course.level && (
                    <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded">
                      {course.level}
                    </span>
                  )}
                </div>
                <Button
                  onClick={() => handleEnroll(course.id)}
                  disabled={enrolling === course.id}
                  className="w-full"
                >
                  {enrolling === course.id ? (
                    <>
                      <Loader className="w-4 h-4 mr-2 animate-spin" />
                      Đang gửi...
                    </>
                  ) : (
                    'Đăng ký'
                  )}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  const renderMyCoursesTab = () => (
    <div className="space-y-4">
      {loading ? (
        <div className="flex justify-center py-8">
          <Loader className="animate-spin w-8 h-8" />
        </div>
      ) : enrollments.length === 0 ? (
        <Card className="p-8 text-center text-gray-500">
          Bạn chưa được chấp nhận vào khóa học nào
        </Card>
      ) : (
        <div className="space-y-3">
          {enrollments.map((enrollment) => (
            <Card key={enrollment.id} className="p-4 flex items-center justify-between hover:shadow-md transition-shadow cursor-pointer">
              <div 
                className="flex-1"
                onClick={() => router.push(`/lms/student/courses/${enrollment.course_id}`)}
              >
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle2 className="w-5 h-5 text-green-600" />
                  <h3 className="font-semibold">{enrollment.course_title}</h3>
                </div>
                {enrollment.teacher_name && (
                  <p className="text-sm text-gray-600">Giáo viên: {enrollment.teacher_name}</p>
                )}
              </div>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => router.push(`/lms/student/courses/${enrollment.course_id}`)}
              >
                Vào khóa học
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  const renderPendingTab = () => (
    <div className="space-y-4">
      {loading ? (
        <div className="flex justify-center py-8">
          <Loader className="animate-spin w-8 h-8" />
        </div>
      ) : enrollments.length === 0 ? (
        <Card className="p-8 text-center text-gray-500">
          Không có yêu cầu đang chờ xác nhận
        </Card>
      ) : (
        <div className="space-y-3">
          {enrollments.map((enrollment) => (
            <Card key={enrollment.id} className="p-4 flex items-center justify-between hover:shadow-md transition-shadow">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-5 h-5 text-yellow-600" />
                  <h3 className="font-semibold">{enrollment.course_title}</h3>
                </div>
                {enrollment.teacher_name && (
                  <p className="text-sm text-gray-600">Giáo viên: {enrollment.teacher_name}</p>
                )}
                <p className="text-xs text-gray-500 mt-1">
                  Đã yêu cầu: {new Date(enrollment.enrolled_at).toLocaleDateString('vi-VN')}
                </p>
              </div>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleCancelEnrollment(enrollment.id)}
                disabled={cancelingId === enrollment.id}
              >
                {cancelingId === enrollment.id ? (
                  <Loader className="w-4 h-4 animate-spin" />
                ) : (
                  'Hủy'
                )}
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-transparent">
      {/* Header */}
      <header className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-3">
              <span className="text-3xl">🎓</span>
              <div>
                <h1 className="text-2xl font-bold text-gray-800">Quản lý khóa học</h1>
                <p className="text-sm text-gray-500">Xin chào, {userName}</p>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <Button
                onClick={handleBackToHome}
                variant="outline"
                size="sm"
              >
                🏠 Trang chủ
              </Button>
              <Button
                onClick={handleChangeRole}
                variant="outline"
                size="sm"
              >
                🔄 Đổi vai trò
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Tabs */}
        <div className="flex gap-4 mb-6 border-b bg-white rounded-t-lg p-4">
          {[
            { id: 'discover', label: 'Khám phá' },
            { id: 'my-courses', label: 'Khóa học của tôi' },
            { id: 'pending', label: 'Chờ xác nhận' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as TabType)}
              className={`px-4 py-3 font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="bg-white rounded-b-lg p-4">
          {activeTab === 'discover' && renderDiscoverTab()}
          {activeTab === 'my-courses' && renderMyCoursesTab()}
          {activeTab === 'pending' && renderPendingTab()}
        </div>
      </main>
    </div>
  );
}