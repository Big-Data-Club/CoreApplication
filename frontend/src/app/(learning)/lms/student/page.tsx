"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { lmsService } from "@/services/lmsService";
import {
  BookOpen, Clock, CheckCircle2,
  ChevronRight, Search, RefreshCw,
} from "lucide-react";
import {
  StatCard, Card,
  ProgressBar, PrimaryBtn, GhostBtn,
  EmptyState, PageLoader, Alert,
  InfiniteScrollTrigger
} from "@/components/lms/shared";
import { Enrollment } from "@/types";

// ─── Stats row ────────────────────────────────────────────────────────────────

function LearningStats({ enrollments }: { enrollments: Enrollment[] }) {
  const accepted = enrollments.filter(e => e.status === "ACCEPTED");

  return (
    <div className="grid grid-cols-3 lg:grid-cols-3 gap-4">
      <StatCard
        label="Đã đăng ký"
        value={accepted.length}
        sub="khóa học"
        icon={<BookOpen className="w-5 h-5" />}
        accent="blue"
      />
      <StatCard
        label="Đang học"
        value={accepted.filter(e => (e.progress_percent || 0) < 100).length}
        sub="khóa đang tiến hành"
        icon={<Clock className="w-5 h-5" />}
        accent="orange"
      />
      <StatCard
        label="Hoàn thành"
        value={accepted.filter(e => (e.progress_percent || 0) === 100).length}
        sub="khóa học"
        icon={<CheckCircle2 className="w-5 h-5" />}
        accent="green"
      />
    </div>
  );
}

// ─── Enrolled course item ─────────────────────────────────────────────────────

function EnrolledCourseItem({
  enrollment,
  onOpen
}: { enrollment: Enrollment; onOpen: (id: number) => void }) {
  return (
    <div
      className="flex items-center gap-4 p-4 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors cursor-pointer group"
      onClick={() => onOpen(enrollment.course_id)}
    >
      {/* Icon */}
      <div className="w-12 h-12 rounded-xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center flex-shrink-0">
        <BookOpen className="w-6 h-6 text-blue-600 dark:text-blue-400" />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-slate-900 dark:text-slate-50 truncate">
          {enrollment.course_title ?? `Khóa học #${enrollment.course_id}`}
        </p>
        {enrollment.teacher_name && (
          <p className="text-xs text-slate-500 dark:text-slate-500 mt-0.5">
            {enrollment.teacher_name}
          </p>
        )}
        <ProgressBar value={enrollment.progress_percent || 0} max={100} color="blue" showPercent={true} className="mt-2" />
      </div>

      {/* Arrow */}
      <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-blue-600 transition-colors flex-shrink-0" />
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function StudentDashboard() {
  const router = useRouter();

  const [allEnrollments, setAllEnrollments] = useState<Enrollment[]>([]);
  const [acceptedEnrollments, setAcceptedEnrollments] = useState<Enrollment[]>([]);

  const [loadingEnrolled, setLoadingEnrolled] = useState(true);
  const [error, setError] = useState("");

  const [limit, setLimit] = useState(15);

  // ── Init ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    loadAllEnrollments();
  }, []);

  const loadAllEnrollments = useCallback(async () => {
    setLoadingEnrolled(true);
    try {
      const [accepted] = await Promise.all([
        lmsService.getMyEnrollments("ACCEPTED"),
      ]);
      setAcceptedEnrollments(accepted || []);
      setAllEnrollments([...(accepted || [])]);
      setLimit(15);
    } catch {
      setError("Không thể tải dữ liệu. Vui lòng thử lại.");
    } finally {
      setLoadingEnrolled(false);
    }
  }, []);

  const displayedEnrollments = acceptedEnrollments.slice(0, limit);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-slate-50 leading-tight">
            Khóa học của tôi
          </h1>
          <p className="text-slate-600 dark:text-slate-400 mt-1">
            Tiếp tục lộ trình học tập của bạn hôm nay.
          </p>
        </div>
        <GhostBtn
          size="sm"
          icon={<RefreshCw className="w-3.5 h-3.5" />}
          onClick={loadAllEnrollments}
        >
          Làm mới
        </GhostBtn>
      </div>

      {/* ── Error alert ── */}
      {error && <Alert type="error">{error}</Alert>}

      {/* ── Stats row ── */}
      {loadingEnrolled ? (
        <div className="grid grid-cols-3 gap-4">
          {[0, 1, 2].map(i => (
            <div key={i} className="h-24 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 animate-pulse" />
          ))}
        </div>
      ) : (
        <LearningStats enrollments={allEnrollments} />
      )}

      {/* ── Enrolled courses ── */}
      <Card className="overflow-hidden">
        <div className="px-6 pt-5 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-slate-50">
                Khóa học đang học
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {acceptedEnrollments.length} khóa học
              </p>
            </div>
          </div>
        </div>

        <div className="p-6">
          {loadingEnrolled ? <PageLoader /> :
          acceptedEnrollments.length === 0 ? (
            <EmptyState
              icon={<BookOpen className="w-14 h-14" />}
              title="Chưa học khóa nào"
              description="Hãy khám phá và đăng ký khóa học phù hợp với bạn."
              action={
                <PrimaryBtn icon={<Search className="w-4 h-4" />} onClick={() => router.push("/lms/student/discover")}>
                  Khám phá khóa học
                </PrimaryBtn>
              }
            />
          ) : (
            <div className="space-y-1 divide-y divide-slate-100 dark:divide-slate-800">
              {displayedEnrollments.map(en => (
                <EnrolledCourseItem
                  key={en.id}
                  enrollment={en}
                  onOpen={id => router.push(`/lms/student/courses/${id}`)}
                />
              ))}
              <InfiniteScrollTrigger
                key={limit}
                hasMore={limit < acceptedEnrollments.length}
                onLoadMore={() => setLimit(l => l + 15)}
              />
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}