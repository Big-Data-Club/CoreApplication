"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import quizService from "@/services/quizService";
import { Clock, CheckCircle, XCircle, Eye, Calendar, Timer, Award, TrendingUp, AlertCircle } from "lucide-react";

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

interface QuizHistoryModalProps {
  quizId: number;
  quizTitle: string;
  onClose: () => void;
  onViewAttempt: (attemptId: number) => void;
}

export default function QuizHistoryModal({
  quizId,
  quizTitle,
  onClose,
  onViewAttempt,
}: QuizHistoryModalProps) {
  const [attempts, setAttempts] = useState<QuizAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadAttempts();
  }, [quizId]);

  const loadAttempts = async () => {
    try {
      setLoading(true);
      setError(""); // Clear previous errors
      
      console.log("Loading attempts for quiz:", quizId);
      
      // Check if auth token exists
      const cookies = document.cookie.split(';');
      const authCookie = cookies.find(c => c.trim().startsWith('authToken='));
      console.log("Auth token exists:", !!authCookie);
      
      const response = await quizService.getMyQuizAttempts(quizId);
      console.log("Attempts response:", response);
      
      setAttempts(response.data || []);
    } catch (err: any) {
      console.error("Error loading attempts:", err);
      console.error("Error response:", err.response);
      
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
  console.log(bestAttempt)
  const averageScore = getAverageScore();

  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-[60] p-4">
      <div className="bg-white rounded-2xl max-w-5xl w-full max-h-[90vh] overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-purple-600 p-6 text-white">
          <div className="flex justify-between items-start mb-4">
            <div className="flex-1">
              <h2 className="text-2xl font-bold mb-2">{quizTitle}</h2>
              <p className="text-blue-100 text-sm">Lịch sử làm bài quiz</p>
            </div>
            <Button
              onClick={onClose}
              className="bg-white bg-opacity-20 hover:bg-opacity-30 text-white border-0 rounded-lg"
            >
              Đóng
            </Button>
          </div>

          {/* Statistics */}
          {attempts.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              <div className="bg-transparent bg-opacity-20 rounded-xl p-4 backdrop-blur-sm">
                <div className="flex items-center gap-2 mb-2">
                  <Calendar className="w-5 h-5" />
                  <span className="text-sm font-medium">Tổng số lần làm</span>
                </div>
                <p className="text-3xl font-bold">{attempts.length}</p>
              </div>

              {averageScore && (
                <div className="bg-transparent bg-opacity-20 rounded-xl p-4 backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="w-5 h-5" />
                    <span className="text-sm font-medium">Điểm trung bình</span>
                  </div>
                  <p className="text-3xl font-bold">{averageScore}%</p>
                </div>
              )}

              {bestAttempt && (
                <div className="bg-transparent bg-opacity-20 rounded-xl p-4 backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <Award className="w-5 h-5" />
                    <span className="text-sm font-medium">Điểm cao nhất</span>
                  </div>
                  <p className="text-3xl font-bold">{bestAttempt.percentage?.toFixed(1)}%</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-280px)]">
          {loading ? (
            <div className="flex justify-center items-center py-12">
              <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
              <XCircle className="w-12 h-12 text-red-500 mx-auto mb-3" />
              <p className="text-red-700 font-medium mb-2">{error}</p>
              <Button
                onClick={loadAttempts}
                className="mt-4 bg-blue-600 hover:bg-blue-700 text-white"
              >
                Thử lại
              </Button>
            </div>
          ) : attempts.length === 0 ? (
            <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-xl p-12 text-center">
              <Clock className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600 font-medium text-lg mb-2">Chưa có lịch sử làm bài</p>
              <p className="text-gray-500 text-sm">Bạn chưa làm quiz này lần nào</p>
            </div>
          ) : (
            <div className="space-y-3">
              {attempts.map((attempt, index) => (
                <div
                  key={attempt.id}
                  className={`border-2 rounded-xl p-5 transition-all hover:shadow-lg ${
                    bestAttempt?.id === attempt.id
                      ? "border-yellow-400 bg-yellow-50"
                      : "border-gray-200 bg-white hover:border-blue-300"
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center text-white font-bold text-lg shadow-md">
                        #{attempt.attempt_number}
                      </div>
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-bold text-gray-800">Lần {attempt.attempt_number}</h3>
                          {getStatusBadge(attempt.status, attempt.is_passed)}
                          {bestAttempt?.id === attempt.id && (
                            <span className="px-2 py-1 bg-yellow-400 text-yellow-900 rounded-full text-xs font-bold flex items-center gap-1">
                              <Award className="w-3 h-3" />
                              Cao nhất
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-4 text-sm text-gray-600">
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

                    <Button
                      onClick={() => onViewAttempt(attempt.id)}
                      size="sm"
                      className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2"
                    >
                      <Eye className="w-4 h-4" />
                      Xem chi tiết
                    </Button>
                  </div>

                  {/* Score Info */}
                  {attempt.status === "GRADED" && attempt.percentage !== null && (
                    <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <p className="text-xs text-gray-600 mb-1">Điểm số</p>
                          <p className="font-bold text-lg text-gray-800">
                            {attempt.earned_points?.toFixed(1)}/{attempt.quiz_total_points}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-600 mb-1">Phần trăm</p>
                          <p className="font-bold text-lg text-gray-800">{attempt.percentage.toFixed(1)}%</p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-600 mb-1">Đúng/Sai</p>
                          <p className="font-bold text-lg">
                            <span className="text-green-600">{attempt.correct_answers}</span>
                            {" / "}
                            <span className="text-red-600">
                              {attempt.answered_questions - attempt.correct_answers}
                            </span>
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-600 mb-1">Điểm chuẩn</p>
                          <p className="font-bold text-lg text-gray-800">
                            {attempt.passing_score?.toFixed(0) || 0}%
                          </p>
                        </div>
                      </div>

                      {/* Progress Bar */}
                      <div className="mt-3">
                        <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
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
    </div>
  );
}