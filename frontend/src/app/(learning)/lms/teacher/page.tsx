"use client";

/**
 * Teacher LMS Dashboard
 *
 * Sections:
 *   1. Header with greeting
 *   2. Stats row
 *   3. Quick actions
 *   4. Recent courses
 *   5. Cross-course Knowledge Graph (all my courses)
 */

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import lmsService from "@/services/lmsService";
import {
  BookOpen, Users, CheckCircle2,
  Plus, Settings, ChevronRight,
  TrendingUp, RefreshCw, LogOut, Home
} from "lucide-react";
import {
  StatCard, Card, SectionHeader,
  Badge, PrimaryBtn, SecondaryBtn, GhostBtn,
  EmptyState, PageLoader, Alert,
} from "@/components/lms/shared";
import { Course } from "@/types";
import { getCookie } from "@/utils/cookies";

// ─── Types ────────────────────────────────────────────────────────────────────

interface TeacherStats {
  totalCourses: number;
  publishedCourses: number;
  draftCourses: number;
  totalStudents: number;
  pendingEnrollments: number;
}

// ─── Quick action card ────────────────────────────────────────────────────────

function ActionCard({
  icon, title, description, badge, onClick, variant = "default",
}: {
  icon: React.ReactNode; title: string; description: string;
  badge?: number; onClick: () => void;
  variant?: "default" | "primary" | "success" | "warning";
}) {
  const VARIANT = {
    default: "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700",
    primary: "border-blue-200 dark:border-blue-800 hover:border-blue-400 dark:hover:border-blue-600 bg-blue-50/50 dark:bg-blue-900/10",
    success: "border-green-200 dark:border-green-800 hover:border-green-400 dark:hover:border-green-600 bg-green-50/50 dark:bg-green-900/10",
    warning: "border-yellow-200 dark:border-yellow-800 hover:border-yellow-400 dark:hover:border-yellow-600 bg-yellow-50/50 dark:bg-yellow-900/10",
  };
  return (
    <button
      onClick={onClick}
      className={`relative flex items-start gap-4 p-5 rounded-2xl border transition-all active:scale-95 hover:shadow-sm w-full text-left ${VARIANT[variant]}`}
    >
      {badge !== undefined && badge > 0 && (
        <span className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center z-10">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
      <div className="text-2xl flex-shrink-0 mt-0.5">{icon}</div>
      <div>
        <p className="font-semibold text-slate-800 dark:text-slate-200 text-sm">{title}</p>
        <p className="text-xs text-slate-500 dark:text-slate-500 mt-0.5">{description}</p>
      </div>
    </button>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────────

export default function TeacherDashboard() {
  const router = useRouter();
  const [userName, setUserName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [stats, setStats] = useState<TeacherStats>({
    totalCourses: 0, publishedCourses: 0, draftCourses: 0,
    totalStudents: 0, pendingEnrollments: 0,
  });
  const [recentCourses, setRecentCourses] = useState<Course[]>([]);

  useEffect(() => {
    const role = sessionStorage.getItem("lms_selected_role");
    if (role !== "TEACHER" && role !== "ADMIN") { router.push("/lms"); return; }
    setUserName(getCookie("userName") || "giảng viên");
    loadDashboard();
  }, []);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const coursesRes = await lmsService.listMyCourses({ page_size: 100 });
      const courses: Course[] = coursesRes?.data ?? [];

      const published = courses.filter(c => c.status === "PUBLISHED");
      const draft = courses.filter(c => c.status === "DRAFT");

      let totalStudents = 0;
      const learnerPromises = published.slice(0, 10).map(course =>
        lmsService.getCourseLearners(course.id, "ACCEPTED").catch(() => [])
      );
      const learnersArrays = await Promise.all(learnerPromises);
      totalStudents = learnersArrays.reduce((sum, learners) => sum + (learners ?? []).length, 0);

      setStats({
        totalCourses: courses.length, publishedCourses: published.length,
        draftCourses: draft.length, totalStudents, pendingEnrollments: 0,
      });

      setRecentCourses(
        [...courses]
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, 6)
      );

    } catch {
      setError("Không thể tải dữ liệu. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }, []);

  if (loading) return <PageLoader message="Đang tải dashboard..." />;

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Chào buổi sáng" : hour < 18 ? "Chào buổi chiều" : "Chào buổi tối";

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">

        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-500 uppercase tracking-wider font-semibold mb-1">Giảng viên</p>
            <h1 className="text-3xl font-extrabold text-slate-900 dark:text-slate-50 leading-tight">
              {greeting}, {userName} 👨‍🏫
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <SecondaryBtn size="sm" icon={<RefreshCw className="w-4 h-4" />} onClick={loadDashboard}>Làm mới</SecondaryBtn>
            <GhostBtn size="sm" icon={<Home className="w-4 h-4" />} onClick={() => router.push("/")}>Trang chủ</GhostBtn>
            <GhostBtn size="sm" icon={<LogOut className="w-4 h-4" />}
              onClick={() => { sessionStorage.removeItem("lms_selected_role"); router.push("/lms"); }}>
              Đổi vai trò
            </GhostBtn>
          </div>
        </div>

        {error && <Alert type="error">{error}</Alert>}

        {/* ── Stats ── */}
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Tổng khóa học" value={stats.totalCourses}
            sub={`${stats.draftCourses} nháp`}
            icon={<BookOpen className="w-5 h-5" />} accent="blue" />
          <StatCard label="Đã xuất bản" value={stats.publishedCourses}
            icon={<CheckCircle2 className="w-5 h-5" />} accent="green"
            trend={stats.publishedCourses > 0 ? { value: "Đang hoạt động", up: true } : undefined} />
          <StatCard label="Tổng học viên" value={stats.totalStudents}
            sub="đã được chấp nhận"
            icon={<Users className="w-5 h-5" />} accent="purple" />
        </div>

        {/* ── Quick actions ── */}
        <Card className="p-6">
          <SectionHeader title="Thao tác nhanh" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <ActionCard icon={<Plus className="w-6 h-6 text-blue-600" />}
              title="Tạo khóa học" description="Thêm khóa học mới" variant="primary"
              onClick={() => router.push("/lms/teacher/courses/create")} />
            <ActionCard icon={<BookOpen className="w-6 h-6 text-slate-600" />}
              title="Quản lý khóa học" description="Xem và chỉnh sửa"
              onClick={() => router.push("/lms/teacher/courses")} />
            <ActionCard icon={<TrendingUp className="w-6 h-6 text-green-600" />}
              title="Thống kê" description="Xem báo cáo chi tiết" variant="success"
              onClick={() => router.push("/lms/teacher/analytics")} />
          </div>
        </Card>

        {/* ── Recent courses ── */}
        <Card className="p-6">
          <SectionHeader
            title="Khóa học gần đây"
            action={
              <GhostBtn size="sm" icon={<ChevronRight className="w-4 h-4" />}
                onClick={() => router.push("/lms/teacher/courses")}>
                Xem tất cả
              </GhostBtn>
            }
          />
          {recentCourses.length === 0 ? (
            <EmptyState icon={<BookOpen className="w-10 h-10" />}
              title="Chưa có khóa học"
              description="Hãy tạo khóa học đầu tiên của bạn."
              action={
                <PrimaryBtn size="sm" icon={<Plus className="w-4 h-4" />}
                  onClick={() => router.push("/lms/teacher/courses/create")}>
                  Tạo khóa học
                </PrimaryBtn>
              } />
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {recentCourses.map(course => (
                <div key={course.id}
                  className="flex items-center gap-3 py-3 cursor-pointer group"
                  onClick={() => router.push(`/lms/teacher/courses/${course.id}`)}>
                  <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center flex-shrink-0">
                    <BookOpen className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-50 truncate">{course.title}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <Badge variant={course.status === "PUBLISHED" ? "green" : "yellow"}>
                        {course.status === "PUBLISHED" ? "Đã xuất bản" : "Nháp"}
                      </Badge>
                      {course.category && <span className="text-xs text-slate-500">{course.category}</span>}
                    </div>
                  </div>
                  <button className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 opacity-0 group-hover:opacity-100 transition-all"
                    onClick={e => { e.stopPropagation(); router.push(`/lms/teacher/courses/${course.id}`); }}>
                    <Settings className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}