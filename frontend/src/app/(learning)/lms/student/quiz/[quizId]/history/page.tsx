"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import quizService from "@/services/quizService";
import { Clock, CheckCircle, XCircle, Eye, Calendar, Timer, Award, TrendingUp, AlertCircle, ArrowLeft } from "lucide-react";

interface QuizAttempt {
  id: number;
  quiz_id: number;
  student_id: number;
  attempt_number: number;
  started_at: string;
  submitted_at: string | null;
  time_spent_seconds: number | null;
  total_points: number | null;
  earned_points: number | null;
  percentage: number | null;
  is_passed: boolean | null;
  status: string;
  quiz_title: string;
  quiz_total_points: number;
  passing_score: number | null;
  answered_questions: number;
  correct_answers: number;
}

export default function QuizHistoryPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = parseInt(params.quizId as string);

  const [attempts, setAttempts] = useState<QuizAttempt[]>([]);
  const [quizTitle, setQuizTitle] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadAttempts();
  }, [quizId]);

  const loadAttempts = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await quizService.getMyQuizAttempts(quizId);
      const attemptsData = response.data || [];
      setAttempts(attemptsData);
      
      if (attemptsData.length > 0) {
        setQuizTitle(attemptsData[0].quiz_title);
      } else {
        // Load quiz info if no attempts
        const quizResponse = await quizService.getQuiz(quizId);
        setQuizTitle(quizResponse.data?.title || "Quiz");
      }
    } catch (err: any) {
      console.error("Error loading attempts:", err);
      if (err.response?.status === 401) {
        setError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
      } else {
        setError(err.response?.data?.error || err.message || "Không thể tải lịch sử làm bài");
      }
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return "0 phút";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
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

  const getStatusBadge = (status: string, isPassed: boolean | null) => {
    if (status === "IN_PROGRESS") {
      return (
        <span className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded-full text-xs font-semibold flex items-center gap-1">
          <Clock className="w-3 h-3" />
          Đang làm
        </span>
      );
    }
    if (status === "SUBMITTED") {
      return (
        <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-semibold flex items-center gap-1">
          <AlertCircle className="w-3 h-3" />
          Chờ chấm
        </span>
      );
    }
    if (status === "GRADED") {
      if (isPassed === true) {
        return (
          <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-xs font-semibold flex items-center gap-1">
            <CheckCircle className="w-3 h-3" />
            Đạt
          </span>
        );
      } else if (isPassed === false) {
        return (
          <span className="px-3 py-1 bg-red-100 text-red-700 rounded-full text-xs font-semibold flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            Không đạt
          </span>
        );
      }
      return (
        <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-xs font-semibold">
          Đã chấm
        </span>
      );
    }
    return (
      <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-xs font-semibold">
        {status}
      </span>
    );
  };

  const getBestAttempt = () => {
    if (attempts.length === 0) return null;
    const gradedAttempts = attempts.filter((a) => a.status === "GRADED" && a.percentage !== null);
    if (gradedAttempts.length === 0) return null;
    return gradedAttempts.reduce((best, current) => {
      return (current.percentage || 0) > (best.percentage || 0) ? current : best;
    });
  };

  const getAverageScore = () => {
    const gradedAttempts = attempts.filter((a) => a.status === "GRADED" && a.percentage !== null);
    if (gradedAttempts.length === 0) return null;
    const sum = gradedAttempts.reduce((acc, a) => acc + (a.percentage || 0), 0);
    return (sum / gradedAttempts.length).toFixed(1);
  };

  const bestAttempt = getBestAttempt();
  const averageScore = getAverageScore();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="mt-4 text-gray-600 font-medium">Đang tải lịch sử...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-transparent">
      {/* Header */}
      <div className="bg-transparent text-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="mb-4">
            <Button
              onClick={() => router.back()}
              variant="ghost"
              className="text-gray-800 hover:bg-white hover:bg-opacity-20"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Quay lại
            </Button>
          </div>

          <div className="mb-6">
            <h1 className="text-3xl font-bold mb-2">{quizTitle}</h1>
            <p className="text-black">Lịch sử làm bài quiz</p>
          </div>

          {/* Statistics */}
          {attempts.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white bg-opacity-20 rounded-xl p-6 backdrop-blur-sm">
                <div className="flex items-center gap-2 mb-2">
                  <Calendar className="w-6 h-6" />
                  <span className="text-sm font-medium">Tổng số lần làm</span>
                </div>
                <p className="text-4xl font-bold">{attempts.length}</p>
              </div>

              {averageScore && (
                <div className="bg-white bg-opacity-20 rounded-xl p-6 backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="w-6 h-6" />
                    <span className="text-sm font-medium">Điểm trung bình</span>
                  </div>
                  <p className="text-4xl font-bold">{averageScore}%</p>
                </div>
              )}

              {bestAttempt && (
                <div className="bg-white bg-opacity-20 rounded-xl p-6 backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <Award className="w-6 h-6" />
                    <span className="text-sm font-medium">Điểm cao nhất</span>
                  </div>
                  <p className="text-4xl font-bold">{bestAttempt.percentage?.toFixed(1)}%</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error ? (
          <div className="bg-red-50 border-2 border-red-200 rounded-xl p-8 text-center">
            <XCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-red-700 mb-2">Có lỗi xảy ra</h3>
            <p className="text-red-600 mb-4">{error}</p>
            <Button
              onClick={loadAttempts}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              Thử lại
            </Button>
          </div>
        ) : attempts.length === 0 ? (
          <div className="bg-white border-2 border-dashed border-gray-300 rounded-xl p-12 text-center">
            <Clock className="w-20 h-20 text-gray-400 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-gray-700 mb-2">Chưa có lịch sử làm bài</h3>
            <p className="text-gray-500 mb-6">Bạn chưa làm quiz này lần nào</p>
            <Button
              onClick={() => router.push(`/lms/student/quiz/${quizId}/take`)}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              Bắt đầu làm bài
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {attempts.map((attempt) => (
              <div
                key={attempt.id}
                className={`bg-white border-2 rounded-xl p-6 transition-all hover:shadow-lg ${
                  bestAttempt?.id === attempt.id
                    ? "border-yellow-400 bg-yellow-50"
                    : "border-gray-200 hover:border-blue-300"
                }`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-4">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center text-white font-bold text-2xl shadow-lg">
                      #{attempt.attempt_number}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="text-xl font-bold text-gray-800">Lần {attempt.attempt_number}</h3>
                        {getStatusBadge(attempt.status, attempt.is_passed)}
                        {bestAttempt?.id === attempt.id && (
                          <span className="px-3 py-1 bg-yellow-400 text-yellow-900 rounded-full text-xs font-bold flex items-center gap-1">
                            <Award className="w-4 h-4" />
                            Cao nhất
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-6 text-sm text-gray-600">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-4 h-4" />
                          {formatDate(attempt.started_at)}
                        </span>
                        {attempt.time_spent_seconds && (
                          <span className="flex items-center gap-1">
                            <Timer className="w-4 h-4" />
                            {formatDuration(attempt.time_spent_seconds)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* ===== DYNAMIC BUTTON BASED ON STATUS ===== */}
                  {attempt.status === "IN_PROGRESS" ? (
                    <Button
                      onClick={() => router.push(`/lms/student/quiz/${quizId}/take?attemptId=${attempt.id}`)}
                      className="bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg flex items-center gap-2"
                    >
                      <Clock className="w-4 h-4" />
                      Tiếp tục làm
                    </Button>
                  ) : (
                    <Button
                      onClick={() => router.push(`/lms/student/quiz/${quizId}/result/${attempt.id}`)}
                      className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2"
                    >
                      <Eye className="w-4 h-4" />
                      Xem chi tiết
                    </Button>
                  )}
                  {/* ===== END DYNAMIC BUTTON ===== */}
                </div>

                {/* Score Info */}
                {attempt.status === "GRADED" && attempt.percentage !== null && (
                  <div className="mt-4 p-5 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                      <div>
                        <p className="text-xs text-gray-600 mb-1">Điểm số</p>
                        <p className="font-bold text-xl text-gray-800">
                          {attempt.earned_points?.toFixed(1)}/{attempt.quiz_total_points}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-600 mb-1">Phần trăm</p>
                        <p className="font-bold text-xl text-gray-800">{attempt.percentage.toFixed(1)}%</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-600 mb-1">Đúng/Sai</p>
                        <p className="font-bold text-xl">
                          <span className="text-green-600">{attempt.correct_answers}</span>
                          {" / "}
                          <span className="text-red-600">
                            {attempt.answered_questions - attempt.correct_answers}
                          </span>
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-600 mb-1">Điểm chuẩn</p>
                        <p className="font-bold text-xl text-gray-800">
                          {attempt.passing_score?.toFixed(0) || 0}%
                        </p>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="mt-4">
                      <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                        <div
                          className={`h-full transition-all rounded-full ${
                            attempt.is_passed ? "bg-green-500" : "bg-red-500"
                          }`}
                          style={{ width: `${attempt.percentage}%` }}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {attempt.status === "IN_PROGRESS" && (
                  <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <p className="text-sm text-yellow-800 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      Bài làm chưa hoàn thành. Bạn có thể tiếp tục làm bài này.
                    </p>
                  </div>
                )}

                {attempt.status === "SUBMITTED" && (
                  <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                    <p className="text-sm text-blue-800 flex items-center gap-2">
                      <Clock className="w-4 h-4" />
                      Bài làm đã được nộp và đang chờ giáo viên chấm điểm.
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}