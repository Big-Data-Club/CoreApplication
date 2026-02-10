"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import quizService from "@/services/quizService";
import { Button } from "@/components/ui/button";

interface AnswerForGrading {
  id: number;
  attempt_id: number;
  question_id: number;
  answer_data: any;
  points_earned: number | null;
  grader_feedback: string;
  graded_at: string | null;
}

export default function TeacherGradingPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = parseInt(params.quizId as string);

  const [answers, setAnswers] = useState<AnswerForGrading[]>([]);
  const [loading, setLoading] = useState(true);
  const [gradingAnswerId, setGradingAnswerId] = useState<number | null>(null);
  const [gradeForm, setGradeForm] = useState({
    points_earned: 0,
    grader_feedback: "",
  });

  useEffect(() => {
    loadAnswersForGrading();
  }, [quizId]);

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

  const handleGradeAnswer = async (answerId: number) => {
    try {
      await quizService.gradeAnswer(answerId, gradeForm);
      setGradingAnswerId(null);
      setGradeForm({ points_earned: 0, grader_feedback: "" });
      loadAnswersForGrading();
      alert("Đã chấm điểm thành công!");
    } catch (error: any) {
      console.error("Error grading answer:", error);
      alert(error.response?.data?.message || "Không thể chấm điểm");
    }
  };

  const startGrading = (answer: AnswerForGrading, maxPoints: number) => {
    setGradingAnswerId(answer.id);
    setGradeForm({
      points_earned: answer.points_earned || 0,
      grader_feedback: answer.grader_feedback || "",
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="mb-6">
        <Button onClick={() => router.back()} variant="outline" className="mb-4">
          ← Quay lại
        </Button>
        <h1 className="text-3xl font-bold text-gray-900">Chấm bài</h1>
        <p className="text-gray-600 mt-2">
          {answers.length} câu trả lời cần chấm điểm
        </p>
      </div>

      {answers.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <div className="text-6xl mb-4">✅</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Hoàn thành!</h2>
          <p className="text-gray-600">Không còn câu trả lời nào cần chấm điểm</p>
        </div>
      ) : (
        <div className="space-y-6">
          {answers.map((answer) => (
            <div key={answer.id} className="bg-white rounded-xl shadow-sm border p-6">
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded font-semibold text-sm">
                    Answer ID: {answer.id}
                  </span>
                  <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded text-sm">
                    Attempt: {answer.attempt_id}
                  </span>
                  {answer.graded_at && (
                    <span className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm">
                      ✓ Đã chấm
                    </span>
                  )}
                </div>
              </div>

              {/* Student Answer */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Câu trả lời của học sinh:
                </label>
                <div className="bg-gray-50 border rounded-lg p-4">
                  {renderAnswerContent(answer.answer_data)}
                </div>
              </div>

              {/* Grading Form */}
              {gradingAnswerId === answer.id ? (
                <div className="border-t pt-4">
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Điểm *
                      </label>
                      <input
                        type="number"
                        value={gradeForm.points_earned}
                        onChange={(e) => setGradeForm({ ...gradeForm, points_earned: parseFloat(e.target.value) })}
                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                        min="0"
                        step="0.5"
                      />
                    </div>
                  </div>

                  <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Nhận xét
                    </label>
                    <textarea
                      value={gradeForm.grader_feedback}
                      onChange={(e) => setGradeForm({ ...gradeForm, grader_feedback: e.target.value })}
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
                <div className="flex gap-2">
                  <Button
                    onClick={() => startGrading(answer, 10)} // You might want to pass actual max points
                    className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
                  >
                    {answer.graded_at ? 'Chỉnh sửa điểm' : 'Chấm điểm'}
                  </Button>
                  {answer.points_earned !== null && (
                    <div className="flex items-center gap-2 px-4 py-2 bg-green-50 border border-green-200 rounded-lg">
                      <span className="text-sm text-gray-700">Điểm hiện tại:</span>
                      <span className="font-semibold text-green-700">{answer.points_earned}</span>
                    </div>
                  )}
                </div>
              )}

              {answer.grader_feedback && gradingAnswerId !== answer.id && (
                <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                  <p className="text-sm font-medium text-gray-700 mb-1">Nhận xét đã lưu:</p>
                  <p className="text-sm text-gray-600">{answer.grader_feedback}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  function renderAnswerContent(answerData: any) {
    if (answerData.text) {
      return (
        <p className="text-gray-800 whitespace-pre-wrap">
          {answerData.text}
        </p>
      );
    }

    if (answerData.file_name) {
      return (
        <div>
          <p className="text-sm text-gray-700 mb-2">
            📎 File đã nộp: <span className="font-semibold">{answerData.file_name}</span>
          </p>
          {answerData.file_path && (
            <a
              href={answerData.file_path}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline text-sm"
            >
              Tải xuống file →
            </a>
          )}
        </div>
      );
    }

    return <p className="text-gray-400 italic">Không có dữ liệu</p>;
  }
}