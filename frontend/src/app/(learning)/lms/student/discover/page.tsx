"use client";

import { useEffect, useState, useCallback } from "react";
import { lmsService } from "@/services/lmsService";
import {
  BookOpen, Search, RefreshCw,
} from "lucide-react";
import {
  Card, CourseCard, Badge,
  PrimaryBtn, GhostBtn,
  EmptyState, PageLoader, Alert,
  InfiniteScrollTrigger
} from "@/components/lms/shared";
import { BreadcrumbNav, type BreadcrumbItem } from "@/components/lms/BreadcrumbNav";
import { Course, Enrollment } from "@/types";

// ─── Main page ────────────────────────────────────────────────────────────────

export default function DiscoverPage() {
  const [publishedCourses, setPublishedCourses] = useState<Course[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [loading, setLoading] = useState(true);
  const [enrolling, setEnrolling] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const [limit, setLimit] = useState(15);

  // ── Load data ──────────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [courses, accepted] = await Promise.all([
        lmsService.listPublishedCourses({ page_size: 200 }),
        lmsService.getMyEnrollments("ACCEPTED"),
      ]);
      setPublishedCourses(courses || []);
      setEnrollments(accepted || []);
      setLimit(15);
    } catch {
      setError("Không thể tải danh sách khóa học.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleEnroll = async (courseId: number) => {
    setEnrolling(courseId);
    try {
      await lmsService.enrollCourse(courseId);
      // Reload enrollments to update badges
      const accepted = await lmsService.getMyEnrollments("ACCEPTED");
      setEnrollments(accepted || []);
    } catch (e: any) {
      setError(e?.response?.data?.message || "Đăng ký thất bại.");
    } finally {
      setEnrolling(null);
    }
  };

  const enrolledIds = new Set(enrollments.map(e => e.course_id));

  const filtered = publishedCourses.filter(c =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );

  const displayedCourses = filtered.slice(0, limit);

  // ── Render ─────────────────────────────────────────────────────────────────

  const breadcrumbItems: BreadcrumbItem[] = [
    { label: "Học tập", href: "/lms/student" },
    { label: "Khám phá" },
  ];

  return (
    <div className="space-y-6">
      <BreadcrumbNav items={breadcrumbItems} />

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-slate-50 leading-tight">
            Khám phá khóa học
          </h1>
          <p className="text-slate-600 dark:text-slate-400 mt-1">
            Tìm và đăng ký các khóa học phù hợp với bạn.
          </p>
        </div>
        <GhostBtn
          size="sm"
          icon={<RefreshCw className="w-3.5 h-3.5" />}
          onClick={loadData}
        >
          Làm mới
        </GhostBtn>
      </div>

      {/* ── Error alert ── */}
      {error && <Alert type="error">{error}</Alert>}

      {/* ── Search bar ── */}
      <Card className="p-4">
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setLimit(15); }}
            placeholder="Tìm kiếm khóa học..."
            className="w-full pl-10 pr-4 py-2.5 border border-slate-300 dark:border-slate-700 rounded-xl text-sm
                       bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100
                       placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          />
        </div>
      </Card>

      {/* ── Course list ── */}
      {loading ? (
        <PageLoader />
      ) : filtered.length === 0 ? (
        search ? (
          <EmptyState
            icon={<Search className="w-12 h-12" />}
            title="Không tìm thấy"
            description={`Không có khóa học nào khớp với "${search}".`}
            action={<GhostBtn onClick={() => { setSearch(""); setLimit(15); }}>Xóa bộ lọc</GhostBtn>}
          />
        ) : (
          <EmptyState
            icon={<BookOpen className="w-12 h-12" />}
            title="Chưa có khóa học"
            description="Hiện chưa có khóa học nào được xuất bản."
          />
        )
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {displayedCourses.map(course => {
              const enrolled = enrolledIds.has(course.id);
              return (
                <CourseCard
                  key={course.id}
                  id={course.id}
                  title={course.title}
                  description={course.description}
                  category={course.category}
                  level={course.level}
                  teacherName={course.teacher_name}
                  thumbnailUrl={course.thumbnail_url}
                  actions={
                    enrolled ? (
                      <Badge variant="green">Đã đăng ký</Badge>
                    ) : (
                      <PrimaryBtn
                        size="sm"
                        loading={enrolling === course.id}
                        onClick={e => { e.stopPropagation(); handleEnroll(course.id); }}
                      >
                        Đăng ký
                      </PrimaryBtn>
                    )
                  }
                />
              );
            })}
          </div>
          <InfiniteScrollTrigger
            key={limit}
            hasMore={limit < filtered.length}
            onLoadMore={() => setLimit(l => l + 15)}
          />
        </div>
      )}
    </div>
  );
}
