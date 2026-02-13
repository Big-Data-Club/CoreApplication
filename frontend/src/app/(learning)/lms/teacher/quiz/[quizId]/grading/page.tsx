"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import quizService from "@/services/quizService";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  CheckCircle,
  FileText,
  User,
  Calendar,
  Award,
  MessageSquare,
  Filter,
  Search,
} from "lucide-react";

interface AnswerForGrading {
  id: number;
  attempt_id: number;
  student_id: number;
  student_name: string;
  student_email: string;
  question_id: number;
  question_text: string;
  question_type: string;
  points: number;
  answer_data: any;
  points_earned: number | null;
  feedback: string;
  answered_at: string;
}

export default function TeacherGradingPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = parseInt(params.quizId as string);

  const [answers, setAnswers] = useState<AnswerForGrading[]>([]);
  const [filteredAnswers, setFilteredAnswers] = useState<AnswerForGrading[]>([]);
  const [loading, setLoading] = useState(true);
  const [gradingAnswerId, setGradingAnswerId] = useState<number | null>(null);
  const [gradeForm, setGradeForm] = useState({
    points_earned: 0,
    grader_feedback: "",
  });

  // Filters
  const [filterGraded, setFilterGraded] = useState<"all" | "graded" | "ungraded">("all");
  const [searchStudent, setSearchStudent] = useState("");
  const [filterQuestionType, setFilterQuestionType] = useState<string>("all");

  useEffect(() => {
    loadAnswersForGrading();
  }, [quizId]);

  useEffect(() => {
    applyFilters();
  }, [answers, filterGraded, searchStudent, filterQuestionType]);

  const loadAnswersForGrading = async () => {
    try {
      const data = await quizService.listAnswersForGrading(quizId);
      setAnswers(data.data || []);
      setLoading(false);
    } catch (error) {
      console.error("Error loading answers:", error);
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...answers];

    // Filter by graded status
    if (filterGraded === "graded") {
      filtered = filtered.filter((a) => a.points_earned !== null);
    } else if (filterGraded === "ungraded") {
      filtered = filtered.filter((a) => a.points_earned === null);
    }

    // Filter by student name
    if (searchStudent) {
      filtered = filtered.filter((a) =>
        a.student_name.toLowerCase().includes(searchStudent.toLowerCase())
      );
    }

    // Filter by question type
    if (filterQuestionType !== "all") {
      filtered = filtered.filter((a) => a.question_type === filterQuestionType);
    }

    setFilteredAnswers(filtered);
  };

  const handleGradeAnswer = async (answerId: number) => {
    try {
      await quizService.gradeAnswer(answerId, gradeForm);
      setGradingAnswerId(null);
      setGradeForm({ points_earned: 0, grader_feedback: "" });
      loadAnswersForGrading();
    } catch (error: any) {
      console.error("Error grading answer:", error);
      alert(error.response?.data?.message || "Không thể chấm điểm");
    }
  };

  const startGrading = (answer: AnswerForGrading) => {
    setGradingAnswerId(answer.id);
    setGradeForm({
      points_earned: answer.points_earned || 0,
      grader_feedback: answer.feedback || "",
    });
  };

  const getQuestionTypes = () => {
    const types = new Set(answers.map((a) => a.question_type));
    return Array.from(types);
  };

  const getGradingStats = () => {
    const total = answers.length;
    const graded = answers.filter((a) => a.points_earned !== undefined).length;
    const ungraded = total - graded;
    return { total, graded, ungraded };
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

  const formatQuestionType = (type: string) => {
    const typeMap: Record<string, string> = {
      ESSAY: "Tự luận",
      FILE_UPLOAD: "Nộp file",
      SHORT_ANSWER: "Trả lời ngắn",
    };
    return typeMap[type] || type;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const stats = getGradingStats();

  return (
    <div className="max-w-7xl mx-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <Button onClick={() => router.back()} variant="outline" className="mb-4">
          <ArrowLeft className="w-4 h-4 mr-2" />
          Quay lại
        </Button>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Chấm bài</h1>
        
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <FileText className="w-5 h-5 text-blue-600" />
              <span className="text-sm font-medium text-gray-700">Tổng số</span>
            </div>
            <p className="text-2xl font-bold text-blue-600">{stats.total}</p>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="w-5 h-5 text-green-600" />
              <span className="text-sm font-medium text-gray-700">Đã chấm</span>
            </div>
            <p className="text-2xl font-bold text-green-600">{stats.graded}</p>
          </div>
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <Award className="w-5 h-5 text-yellow-600" />
              <span className="text-sm font-medium text-gray-700">Chưa chấm</span>
            </div>
            <p className="text-2xl font-bold text-yellow-600">{stats.ungraded}</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Filter className="w-5 h-5 text-gray-600" />
          <h3 className="font-semibold text-gray-900">Bộ lọc</h3>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Filter by graded status */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Trạng thái chấm
            </label>
            <select
              value={filterGraded}
              onChange={(e) => setFilterGraded(e.target.value as any)}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Tất cả</option>
              <option value="graded">Đã chấm</option>
              <option value="ungraded">Chưa chấm</option>
            </select>
          </div>

          {/* Search student */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Tìm học sinh
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchStudent}
                onChange={(e) => setSearchStudent(e.target.value)}
                placeholder="Tên hoặc email..."
                className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Filter by question type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Loại câu hỏi
            </label>
            <select
              value={filterQuestionType}
              onChange={(e) => setFilterQuestionType(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Tất cả</option>
              {getQuestionTypes().map((type) => (
                <option key={type} value={type}>
                  {formatQuestionType(type)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <p className="text-sm text-gray-600 mt-4">
          Hiển thị {filteredAnswers.length} / {answers.length} câu trả lời
        </p>
      </div>

      {/* Answers List */}
      {filteredAnswers.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <div className="text-6xl mb-4">✅</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            {answers.length === 0 ? "Không có câu trả lời nào" : "Không tìm thấy kết quả"}
          </h2>
          <p className="text-gray-600">
            {answers.length === 0
              ? "Không có câu trả lời nào cần chấm điểm"
              : "Thử thay đổi bộ lọc để xem các câu trả lời khác"}
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {filteredAnswers.map((answer) => (
            <div key={answer.id} className="bg-white rounded-xl shadow-sm border">
              {/* Header */}
              <div className="bg-gray-50 border-b px-6 py-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-gray-600" />
                        <span className="font-semibold text-gray-900">
                          {answer.student_name}
                        </span>
                      </div>
                      <span className="text-sm text-gray-500">{answer.student_email}</span>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-gray-600">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-4 h-4" />
                        {formatDate(answer.answered_at)}
                      </span>
                      <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">
                        {formatQuestionType(answer.question_type)}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    {answer.points_earned !== undefined ? (
                      <div className="px-4 py-2 bg-green-100 text-green-700 rounded-lg">
                        <p className="text-sm font-medium">Đã chấm</p>
                        <p className="text-lg font-bold">
                          {answer.points_earned}/{answer.points} điểm
                        </p>
                      </div>
                    ) : (
                      <div className="px-4 py-2 bg-yellow-100 text-yellow-700 rounded-lg">
                        <p className="text-sm font-medium">Chưa chấm</p>
                        <p className="text-lg font-bold">Tối đa: {answer.points} điểm</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Question */}
              <div className="px-6 py-4 border-b">
                <h3 className="text-sm font-medium text-gray-700 mb-2">Câu hỏi:</h3>
                <p className="text-gray-900 font-medium">{answer.question_text}</p>
              </div>

              {/* Student Answer */}
              <div className="px-6 py-4 border-b">
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  Câu trả lời của học sinh:
                </h3>
                <div className="bg-gray-50 border rounded-lg p-4">
                  {renderAnswerContent(answer.answer_data)}
                </div>
              </div>

              {/* Grading Section */}
              <div className="px-6 py-4">
                {gradingAnswerId === answer.id ? (
                  <div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Điểm <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="number"
                          value={gradeForm.points_earned}
                          onChange={(e) =>
                            setGradeForm({
                              ...gradeForm,
                              points_earned: parseFloat(e.target.value),
                            })
                          }
                          className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                          min="0"
                          max={answer.points}
                          step="0.5"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Tối đa: {answer.points} điểm
                        </p>
                      </div>
                    </div>

                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        <MessageSquare className="w-4 h-4 inline mr-1" />
                        Nhận xét
                      </label>
                      <textarea
                        value={gradeForm.grader_feedback}
                        onChange={(e) =>
                          setGradeForm({ ...gradeForm, grader_feedback: e.target.value })
                        }
                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                        rows={4}
                        placeholder="Nhập nhận xét cho học sinh..."
                      />
                    </div>

                    <div className="flex gap-2">
                      <Button
                        onClick={() => handleGradeAnswer(answer.id)}
                        className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700"
                      >
                        <CheckCircle className="w-4 h-4 mr-2" />
                        Lưu điểm
                      </Button>
                      <Button
                        onClick={() => {
                          setGradingAnswerId(null);
                          setGradeForm({ points_earned: 0, grader_feedback: "" });
                        }}
                        variant="outline"
                      >
                        Hủy
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <Button
                      onClick={() => startGrading(answer)}
                      className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
                    >
                      {answer.points_earned !== null ? "Chỉnh sửa điểm" : "Chấm điểm"}
                    </Button>

                    {answer.feedback && (
                      <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <p className="text-sm font-medium text-gray-700 mb-1 flex items-center gap-2">
                          <MessageSquare className="w-4 h-4" />
                          Nhận xét đã lưu:
                        </p>
                        <p className="text-sm text-gray-700">{answer.feedback}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  function renderAnswerContent(answerData: any) {
    if (answerData.answer_text) {
      return (
        <p className="text-gray-800 whitespace-pre-wrap font-medium">{answerData.answer_text}</p>
      );
    }

    if (answerData.file_name) {
      return (
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <p className="text-sm text-gray-700 mb-1">
              📎 File đã nộp:{" "}
              <span className="font-semibold">{answerData.file_name}</span>
            </p>
            {answerData.file_size && (
              <p className="text-xs text-gray-500">
                Kích thước: {(answerData.file_size / 1024).toFixed(2)} KB
              </p>
            )}
          </div>
          {answerData.file_path && (
            <a
              href={`/files/${answerData.file_path}`}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
            >
              Tải xuống →
            </a>
          )}
        </div>
      );
    }

    return <p className="text-gray-400 italic">Không có dữ liệu</p>;
  }
}