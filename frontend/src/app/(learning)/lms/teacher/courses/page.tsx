"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import lmsService from "@/services/lmsService";
import {
  Plus, Search, BookOpen, Settings, Trash2,
  Eye, EyeOff, ChevronRight
} from "lucide-react";
import {
  Card, Badge, PrimaryBtn, GhostBtn,
  EmptyState, PageLoader, Alert, TabBar, Spinner,
  InfiniteScrollTrigger
} from "@/components/lms/shared";
import { Course } from "@/types";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | "draft" | "published";

// ─── Course row (list item) ───────────────────────────────────────────────────

function CourseRow({
  course, onOpen, onPublish, onDelete, publishing, deleting
}: {
  course: Course;
  onOpen: () => void;
  onPublish: () => void;
  onDelete: () => void;
  publishing: boolean;
  deleting: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-4 px-5 py-4 cursor-pointer group",
        "hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
      )}
      onClick={onOpen}
    >
      {/* Icon */}
      <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center flex-shrink-0">
        <BookOpen className="w-5 h-5 text-blue-600 dark:text-blue-400" />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-0.5">
          <p className="font-semibold text-slate-900 dark:text-slate-50 truncate max-w-xs">
            {course.title}
          </p>
          <Badge variant={course.status === "PUBLISHED" ? "green" : "yellow"}>
            {course.status === "PUBLISHED" ? "Đã xuất bản" : "Nháp"}
          </Badge>
          {course.category && <Badge variant="gray">{course.category}</Badge>}
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-500 truncate">
          {course.description || "Chưa có mô tả"}
        </p>
      </div>

      {/* Actions */}
      <div
        className="flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onPublish}
          disabled={publishing}
          className={cn(
            "p-2 rounded-lg transition-colors text-sm font-medium flex items-center gap-1.5 border",
            course.status === "DRAFT"
              ? "hover:bg-green-50 dark:hover:bg-green-950/20 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800 hover:border-green-300 dark:hover:border-green-700"
              : "hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 border-slate-200 dark:border-slate-800"
          )}
          title={course.status === "DRAFT" ? "Xuất bản" : "Đã xuất bản"}
        >
          {publishing ? (
            <Spinner className="w-4 h-4 border-2" />
          ) : course.status === "DRAFT" ? (
            <Eye className="w-4 h-4" />
          ) : (
            <EyeOff className="w-4 h-4" />
          )}
        </button>

        <button
          onClick={() => {}}
          className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors"
          title="Chỉnh sửa"
        >
          <Settings className="w-4 h-4" />
        </button>

        <button
          onClick={onDelete}
          disabled={deleting}
          className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors"
          title="Xóa"
        >
          {deleting ? <Spinner className="w-4 h-4 border-2" /> : <Trash2 className="w-4 h-4" />}
        </button>

        <ChevronRight className="w-4 h-4 text-slate-400 ml-1" />
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CoursesListPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [courses, setCourses] = useState<Course[]>([]);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [publishing, setPublishing] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const [limit, setLimit] = useState(15);

  const load = useCallback(async (status?: StatusFilter) => {
    setLoading(true);
    setError("");
    try {
      const params = status && status !== "all" ? { status: status.toUpperCase() } : {};
      const res = await lmsService.listMyCourses({ ...params, page_size: 200 });
      setCourses(res?.data ?? []);
      setLimit(15); // Reset limit on new data
    } catch {
      setError("Không thể tải danh sách khóa học.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(filter); }, [filter]);

  const handlePublish = async (course: Course) => {
    if (course.status !== "DRAFT") return;
    if (!confirm(`Xuất bản khóa học "${course.title}"?`)) return;
    setPublishing(course.id);
    try {
      await lmsService.publishCourse(course.id);
      setCourses(prev => prev.map(c => c.id === course.id ? { ...c, status: "PUBLISHED" } : c));
    } catch { setError("Không thể xuất bản."); }
    finally { setPublishing(null); }
  };

  const handleDelete = async (course: Course) => {
    if (!confirm(`Xóa khóa học "${course.title}"? Hành động này không thể hoàn tác.`)) return;
    setDeleting(course.id);
    try {
      await lmsService.deleteCourse(course.id);
      setCourses(prev => prev.filter(c => c.id !== course.id));
    } catch { setError("Không thể xóa khóa học."); }
    finally { setDeleting(null); }
  };

  const filtered = courses.filter(c =>
    c.title.toLowerCase().includes(search.toLowerCase()) ||
    (c.description ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const displayedCourses = filtered.slice(0, limit);

  const published = courses.filter(c => c.status === "PUBLISHED").length;
  const draft = courses.filter(c => c.status === "DRAFT").length;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-900 dark:text-slate-50">Khóa học của tôi</h1>
            <p className="text-slate-600 dark:text-slate-400 mt-1">
              {courses.length} khóa học · {published} đã xuất bản · {draft} nháp
            </p>
          </div>
          <PrimaryBtn
            icon={<Plus className="w-4 h-4" />}
            onClick={() => router.push("/lms/teacher/courses/create")}
          >
            Tạo khóa học mới
          </PrimaryBtn>
        </div>

        {error && <Alert type="error">{error}</Alert>}

        {/* Filter + search card */}
        <Card className="p-4 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <TabBar
            tabs={[
              { id: "all" as StatusFilter,       label: "Tất cả",    badge: courses.length },
              { id: "published" as StatusFilter,  label: "Xuất bản",  badge: published },
              { id: "draft" as StatusFilter,      label: "Nháp",      badge: draft },
            ]}
            active={filter}
            onChange={setFilter}
          />
          <div className="flex-1 sm:max-w-xs relative">
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

        {/* Course list */}
        <Card className="overflow-hidden">
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
                description="Tạo khóa học đầu tiên của bạn để bắt đầu."
                action={
                  <PrimaryBtn
                    icon={<Plus className="w-4 h-4" />}
                    onClick={() => router.push("/lms/teacher/courses/create")}
                  >
                    Tạo khóa học
                  </PrimaryBtn>
                }
              />
            )
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {displayedCourses.map(course => (
                <CourseRow
                  key={course.id}
                  course={course}
                  onOpen={() => router.push(`/lms/teacher/courses/${course.id}`)}
                  onPublish={() => handlePublish(course)}
                  onDelete={() => handleDelete(course)}
                  publishing={publishing === course.id}
                  deleting={deleting === course.id}
                />
              ))}
              <InfiniteScrollTrigger
                key={limit}
                hasMore={limit < filtered.length}
                onLoadMore={() => setLimit(l => l + 15)}
              />
            </div>
          )}
        </Card>

      </div>
    </div>
  );
}