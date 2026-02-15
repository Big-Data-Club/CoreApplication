"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import quizService from "@/services/quizService";
import {
  ArrowLeft,
  Clock,
  CheckCircle,
  XCircle,
  Award,
  Target,
  BarChart3,
  Timer,
  Calendar,
  FileText,
  Home,
  AlertCircle,
  Eye,
} from "lucide-react";
import QuizReviewModal from "@/components/lms/student/QuizReviewModal";

interface AttemptSummary {
  attempt: {
    id: number;
    quiz_id: number;
    attempt_number: number;
    started_at: string;
    submitted_at: string | null;
    status: string;
    quiz_title: string;
    student_name: string;
  };
  question_breakdown: Array<{
    question_id: number;
    question_text: string;
    question_type: string;
    points: number;
    points_earned: number;
    is_correct: boolean;
    time_spent_seconds: number;
    answered_at: string;
  }>;
  time_breakdown: {
    total_seconds: number;
    total_minutes: number;
    average_per_question: number;
    formatted_duration: string;
  };
  score_breakdown: {
    total_points: number;
    earned_points: number;
    percentage: number;
    passing_score: number;
    is_passed: boolean;
    correct_count: number;
    incorrect_count: number;
    ungraded_count: number;
  };
  grading_status: {
    is_fully_graded: boolean;
    pending_grading_count: number;
    is_provisional: boolean;
  };
}

export default function AttemptResultPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = parseInt(params.quizId as string);
  const attemptId = parseInt(params.attemptId as string);

  const [summary, setSummary] = useState<AttemptSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showReview, setShowReview] = useState(false)

  useEffect(() => {
    loadSummary();
  }, [attemptId]);

  const loadSummary = async () => {
    try {
      setLoading(true);
      const response = await quizService.getAttemptSummary(attemptId);
      setSummary(response.data);
    } catch (err: any) {
      console.error("Error loading attempt summary:", err);
      setError(err.response?.data?.error || "Không thể tải thông tin chi tiết");
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString("vi-VN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}m ${secs}s`;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="mt-4 text-gray-600 font-medium">Đang tải kết quả...</p>
        </div>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl max-w-md w-full p-8 shadow-xl border-2 border-red-200">
          <XCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h3 className="text-xl font-bold text-center mb-2">Có lỗi xảy ra</h3>
          <p className="text-center text-gray-600 mb-6">{error || "Không thể tải thông tin"}</p>
          <div className="flex gap-2">
            <Button
              onClick={() => router.push(`/lms/student/quiz/${quizId}/history`)}
              variant="outline"
              className="flex-1"
            >
              Về lịch sử
            </Button>
            <Button
              onClick={loadSummary}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              Thử lại
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const { attempt, question_breakdown, time_breakdown, score_breakdown, grading_status } = summary;

  const getHeaderColor = () => {
    if (grading_status.is_provisional) {
      return "bg-gradient-to-r from-yellow-600 to-orange-600";
    }
    return score_breakdown.is_passed
      ? "bg-gradient-to-r from-green-600 to-emerald-600"
      : "bg-gradient-to-r from-red-600 to-pink-600";
  };

  return (
    <div className="min-h-screen bg-transparent">
      {/* Header */}
      <div className={`text-white ${getHeaderColor()}`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Button
                onClick={() => router.push(`/lms/student/quiz/${quizId}/history`)}
                variant="ghost"
                className="text-white hover:bg-white hover:bg-opacity-20"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Về lịch sử
              </Button>
              <Button
                onClick={() => router.push('/lms/student')}
                variant="ghost"
                className="text-white hover:bg-white hover:bg-opacity-20"
              >
                <Home className="w-4 h-4 mr-2" />
                Trang chủ
              </Button>
            </div>
          </div>

          {/* Thông báo điểm tạm thời */}
          {grading_status.is_provisional && (
            <div className="mb-6 bg-white bg-opacity-20 backdrop-blur-sm rounded-xl p-4">
              <div className="flex items-center gap-3 text-black">
                <AlertCircle className="w-6 h-6" />
                <div>
                  <p className="font-bold text-lg">Điểm tạm thời</p>
                  <p className="text-sm opacity-90">
                    Còn {grading_status.pending_grading_count} câu chưa được chấm. 
                    Điểm hiện tại chỉ mang tính chất tham khảo và có thể thay đổi sau khi giáo viên chấm xong.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="mb-6">
            <h1 className="text-3xl font-bold mb-2">{attempt.quiz_title}</h1>
            <p className="text-white text-opacity-90">
              Lần làm #{attempt.attempt_number} - {formatDate(attempt.started_at)}
            </p>
          </div>

          {/* Score Summary */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-transparent bg-opacity-20 rounded-xl p-6 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <Award className="w-6 h-6" />
                <span className="text-sm font-medium">
                  {grading_status.is_provisional ? "Điểm tạm thời" : "Điểm số"}
                </span>
              </div>
              <p className="text-4xl font-bold">
                {score_breakdown.earned_points.toFixed(1)}/{score_breakdown.total_points}
              </p>
              <p className="text-sm mt-1 opacity-90">{score_breakdown.percentage.toFixed(1)}%</p>
            </div>

            <div className="bg-transparent bg-opacity-20 rounded-xl p-6 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-6 h-6" />
                <span className="text-sm font-medium">Kết quả</span>
              </div>
              <p className="text-4xl font-bold">
                {grading_status.is_provisional 
                  ? "Đang chờ" 
                  : score_breakdown.is_passed ? "Đạt" : "Chưa đạt"}
              </p>
              <p className="text-sm mt-1 opacity-90">
                Chuẩn: {score_breakdown.passing_score.toFixed(0)}%
              </p>
            </div>

            <div className="bg-transparent bg-opacity-20 rounded-xl p-6 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <BarChart3 className="w-6 h-6" />
                <span className="text-sm font-medium">Đúng/Sai</span>
              </div>
              <p className="text-4xl font-bold">
                {score_breakdown.correct_count}/{question_breakdown.length}
              </p>
              <p className="text-sm mt-1 opacity-90">
                Sai: {score_breakdown.incorrect_count}
                {grading_status.pending_grading_count > 0 && 
                  ` | Chờ: ${grading_status.pending_grading_count}`
                }
              </p>
            </div>

            <div className="bg-transparent bg-opacity-20 rounded-xl p-6 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <Timer className="w-6 h-6" />
                <span className="text-sm font-medium">Thời gian</span>
              </div>
              <p className="text-3xl font-bold">{time_breakdown.formatted_duration}</p>
              <p className="text-sm mt-1 opacity-90">
                TB: {formatTime(time_breakdown.average_per_question)}/câu
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Question Breakdown */}
        <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
          <h3 className="text-xl font-bold mb-6 flex items-center gap-2">
            <FileText className="w-6 h-6 text-blue-600" />
            Chi tiết từng câu hỏi
          </h3>

          <div className="space-y-4">
            {question_breakdown.map((q, index) => {
              const isPending = q.points_earned === 0 && 
                (q.question_type === "ESSAY" || 
                 q.question_type === "FILE_UPLOAD" || 
                 q.question_type === "SHORT_ANSWER");
              
              return (
                <div
                  key={q.question_id}
                  className={`border-2 rounded-xl p-5 ${
                    isPending
                      ? "border-yellow-300 bg-yellow-50"
                      : q.is_correct
                      ? "border-green-200 bg-green-50"
                      : q.question_type === "ESSAY" || q.question_type === "SHORT_ANSWER" || q.question_type === "FILE_UPLOAD" 
                      ? "border-yellow-200 bg-yellow-50"
                      : "border-red-200 bg-red-50"
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div
                      className={`w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-lg ${
                        isPending
                          ? "bg-yellow-500"
                          : q.is_correct
                          ? "bg-green-500"
                          : q.question_type === "ESSAY" || q.question_type === "SHORT_ANSWER" || q.question_type === "FILE_UPLOAD" 
                          ? "bg-yellow-500"
                          : "bg-red-500"
                      }`}
                    >
                      {index + 1}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-3">
                        {isPending ? (
                          <>
                            <AlertCircle className="w-5 h-5 text-yellow-600" />
                            <span className="font-bold text-lg text-yellow-800">
                              Đang chờ chấm
                            </span>
                          </>
                        ) : q.is_correct ? (
                          <>
                            <CheckCircle className="w-5 h-5 text-green-600" />
                            <span className="font-bold text-lg text-green-800">Đúng</span>
                          </>
                        ) : q.question_type === "ESSAY" || q.question_type === "SHORT_ANSWER" || q.question_type === "FILE_UPLOAD" ? (
                          <>
                            <XCircle className="w-5 h-5 text-yellow-600" />
                            <span className="font-bold text-lg text-yellow-800">Đã được chấm</span>
                          </>
                        ) : (
                          <>
                            <XCircle className="w-5 h-5 text-red-600" />
                            <span className="font-bold text-lg text-red-800">Sai</span>
                          </>
                        )}

                        <span className="px-3 py-1 bg-white text-xs font-medium rounded-full border">
                          {q.question_type}
                        </span>
                      </div>
                      <p className="text-gray-800 font-medium mb-3 text-lg">{q.question_text}</p>
                      <div className="flex items-center gap-6 text-sm text-gray-600">
                        <span className="flex items-center gap-1">
                          <Award className="w-4 h-4" />
                          {isPending 
                            ? `Chưa chấm (${q.points.toFixed(1)} điểm)` 
                            : `${q.points_earned.toFixed(1)}/${q.points.toFixed(1)} điểm`
                          }
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-4 h-4" />
                          {formatTime(q.time_spent_seconds)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Additional Info */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h4 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-blue-600" />
            Thông tin bổ sung
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-sm text-gray-600 mb-1">Bắt đầu làm bài:</p>
              <p className="font-semibold text-gray-800 text-lg">{formatDate(attempt.started_at)}</p>
            </div>
            {attempt.submitted_at && (
              <div>
                <p className="text-sm text-gray-600 mb-1">Nộp bài:</p>
                <p className="font-semibold text-gray-800 text-lg">{formatDate(attempt.submitted_at)}</p>
              </div>
            )}
            <div>
              <p className="text-sm text-gray-600 mb-1">Trạng thái:</p>
              <p className="font-semibold text-gray-800 text-lg">
                {grading_status.is_provisional ? "Đang chờ chấm" : attempt.status}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600 mb-1">Tổng thời gian:</p>
              <p className="font-semibold text-gray-800 text-lg">
                {time_breakdown.total_minutes} phút ({time_breakdown.total_seconds} giây)
              </p>
            </div>
          </div>
        </div>

        {/* Footer with Review Button */}
        <div className="p-6 bg-gray-50 border-t">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-gray-600">
              Bạn có thể xem chi tiết đáp án và giải thích cho từng câu hỏi
            </p>
            <Button
              onClick={() => setShowReview(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white flex items-center gap-2"
            >
              <Eye className="w-4 h-4" />
              Xem chi tiết bài làm
            </Button>
          </div>
        </div>

        {/* Quiz Review Modal */}
        {showReview && (
          <QuizReviewModal
            attemptId={attemptId}
            onClose={() => setShowReview(false)}
          />
        )}

        {/* Action Buttons */}
        <div className="mt-8 flex gap-4 justify-center">
          <Button
            onClick={() => router.push(`/lms/student/quiz/${quizId}/history`)}
            variant="outline"
            size="lg"
            className="px-8"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Về lịch sử
          </Button>
          <Button
            onClick={() => router.push(`/lms/student/quiz/${quizId}/take?start=true`)}
            size="lg"
            className="px-8 bg-blue-600 hover:bg-blue-700 text-white"
          >
            Làm lại quiz
          </Button>
        </div>
      </div>
    </div>
  );
}