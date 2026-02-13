/* eslint-disable @next/next/no-img-element */
"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import quizService from "@/services/quizService";
import QuizReviewModal from "./QuizReviewModal";
import {
  ArrowLeft,
  Clock,
  CheckCircle,
  XCircle,
  Award,
  TrendingUp,
  Target,
  BarChart3,
  Timer,
  Calendar,
  FileText,
  Eye,
} from "lucide-react";

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
}

interface AttemptSummaryModalProps {
  attemptId: number;
  onClose: () => void;
  onBack?: () => void;
}

export default function AttemptSummaryModal({
  attemptId,
  onClose,
  onBack,
}: AttemptSummaryModalProps) {
  const [summary, setSummary] = useState<AttemptSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showReview, setShowReview] = useState(false);

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
      <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50">
        <div className="bg-white rounded-2xl p-12 shadow-2xl">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-center mt-4 text-gray-600 font-medium">Đang tải thông tin...</p>
        </div>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl max-w-md w-full p-8 shadow-2xl">
          <XCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h3 className="text-xl font-bold text-center mb-2">Có lỗi xảy ra</h3>
          <p className="text-center text-gray-600 mb-6">{error || "Không thể tải thông tin"}</p>
          <Button onClick={onClose} className="w-full bg-blue-600 hover:bg-blue-700 text-white">
            Đóng
          </Button>
        </div>
      </div>
    );
  }

  const { attempt, question_breakdown, time_breakdown, score_breakdown } = summary;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden shadow-2xl">
        {/* Header */}
        <div
          className={`p-6 text-white ${
            score_breakdown.is_passed
              ? "bg-gradient-to-r from-green-600 to-emerald-600"
              : "bg-gradient-to-r from-red-600 to-pink-600"
          }`}
        >
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              {onBack && (
                <Button
                  onClick={onBack}
                  className="bg-white bg-opacity-20 hover:bg-opacity-30 border-0 rounded-lg"
                >
                  <ArrowLeft className="w-4 h-4" />
                </Button>
              )}
              <div>
                <h2 className="text-2xl font-bold mb-1">{attempt.quiz_title}</h2>
                <p className="text-white text-opacity-90 text-sm">
                  Lần làm #{attempt.attempt_number} - {formatDate(attempt.started_at)}
                </p>
              </div>
            </div>
            <Button
              onClick={onClose}
              className="bg-white bg-opacity-20 hover:bg-opacity-30 border-0 rounded-lg"
            >
              Đóng
            </Button>
          </div>

          {/* Score Summary */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
            <div className="bg-transparent bg-opacity-20 rounded-xl p-4 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <Award className="w-5 h-5" />
                <span className="text-sm font-medium">Điểm số</span>
              </div>
              <p className="text-3xl font-bold">
                {score_breakdown.earned_points.toFixed(1)}/{score_breakdown.total_points}
              </p>
              <p className="text-sm mt-1 opacity-90">{score_breakdown.percentage.toFixed(1)}%</p>
            </div>

            <div className="bg-transparent bg-opacity-20 rounded-xl p-4 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-5 h-5" />
                <span className="text-sm font-medium">Kết quả</span>
              </div>
              <p className="text-3xl font-bold">
                {score_breakdown.is_passed ? "Đạt" : "Chưa đạt"}
              </p>
              <p className="text-sm mt-1 opacity-90">
                Chuẩn: {score_breakdown.passing_score.toFixed(0)}%
              </p>
            </div>

            <div className="bg-transparent bg-opacity-20 rounded-xl p-4 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <BarChart3 className="w-5 h-5" />
                <span className="text-sm font-medium">Đúng/Sai</span>
              </div>
              <p className="text-3xl font-bold">
                {score_breakdown.correct_count}/{question_breakdown.length}
              </p>
              <p className="text-sm mt-1 opacity-90">
                Sai: {score_breakdown.incorrect_count}
              </p>
            </div>

            <div className="bg-transparent bg-opacity-20 rounded-xl p-4 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <Timer className="w-5 h-5" />
                <span className="text-sm font-medium">Thời gian</span>
              </div>
              <p className="text-2xl font-bold">{time_breakdown.formatted_duration}</p>
              <p className="text-sm mt-1 opacity-90">
                TB: {formatTime(time_breakdown.average_per_question)}/câu
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-280px)]">
          {/* Question Breakdown */}
          <div className="mb-6">
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-600" />
              Chi tiết từng câu hỏi
            </h3>

            <div className="space-y-3">
              {question_breakdown.map((q, index) => (
                <div
                  key={q.question_id}
                  className={`border-2 rounded-xl p-4 ${
                    q.is_correct
                      ? "border-green-200 bg-green-50"
                      : "border-red-200 bg-red-50"
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-start gap-3 flex-1">
                      <div
                        className={`w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold ${
                          q.is_correct ? "bg-green-500" : "bg-red-500"
                        }`}
                      >
                        {index + 1}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          {q.is_correct ? (
                            <CheckCircle className="w-5 h-5 text-green-600" />
                          ) : (
                            <XCircle className="w-5 h-5 text-red-600" />
                          )}
                          <span
                            className={`font-bold ${
                              q.is_correct ? "text-green-800" : "text-red-800"
                            }`}
                          >
                            {q.is_correct ? "Đúng" : "Sai"}
                          </span>
                          <span className="text-xs bg-white px-2 py-1 rounded-full border">
                            {q.question_type}
                          </span>
                        </div>
                        <p className="text-gray-800 font-medium mb-2">{q.question_text}</p>
                        <div className="flex items-center gap-4 text-sm text-gray-600">
                          <span className="flex items-center gap-1">
                            <Award className="w-4 h-4" />
                            {q.points_earned.toFixed(1)}/{q.points.toFixed(1)} điểm
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-4 h-4" />
                            {formatTime(q.time_spent_seconds)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Additional Info */}
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-5">
            <h4 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-blue-600" />
              Thông tin bổ sung
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-gray-600">Bắt đầu làm bài:</p>
                <p className="font-semibold text-gray-800">{formatDate(attempt.started_at)}</p>
              </div>
              {attempt.submitted_at && (
                <div>
                  <p className="text-gray-600">Nộp bài:</p>
                  <p className="font-semibold text-gray-800">{formatDate(attempt.submitted_at)}</p>
                </div>
              )}
              <div>
                <p className="text-gray-600">Trạng thái:</p>
                <p className="font-semibold text-gray-800">{attempt.status}</p>
              </div>
              <div>
                <p className="text-gray-600">Tổng thời gian:</p>
                <p className="font-semibold text-gray-800">
                  {time_breakdown.total_minutes} phút ({time_breakdown.total_seconds} giây)
                </p>
              </div>
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
      </div>

      {/* Quiz Review Modal */}
      {showReview && (
        <QuizReviewModal
          attemptId={attemptId}
          onClose={() => setShowReview(false)}
        />
      )}
    </div>
  );
}