/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import quizService from "@/services/quizService";
import { Button } from "@/components/ui/button";
import QuestionImageUploader from "@/components/lms/teacher/QuestionImageUploader";
import FillBlankTextEditor from "@/components/lms/teacher/FillBlankTextEditor";
import FillBlankDropdownEditor from "@/components/lms/teacher/FillBlankDropdownEditor";
import type {
  FillBlankTextSettings,
  FillBlankTextCorrectAnswer,
  FillBlankDropdownSettings,
  FillBlankDropdownOption,
} from "@/fillBlankType";

interface Quiz {
  id: number;
  title: string;
  description: string;
  total_points: number;
  time_limit_minutes: number | null;
  max_attempts: number | null;
  passing_score: number | null;
  auto_grade: boolean;
  show_results_immediately: boolean;
  show_correct_answers: boolean;
  allow_review: boolean;
  is_published: boolean;
}

interface QuestionImage {
  id: string;
  url: string;
  file_path: string;
  file_name: string;
  file_size: number;
  mime_type: string;
  position: string;
  caption?: string;
  alt_text?: string;
  display_width?: string;
  created_at: string;
}

interface Question {
  id: number;
  question_type: string;
  question_text: string;
  question_html?: string;
  points: number;
  order_index: number;
  settings?: any;
  answer_options: any[];
  correct_answers: any[];
}

// Extended answer option interface with blank_id
interface AnswerOption {
  option_text: string;
  is_correct: boolean;
  order_index: number;
  blank_id?: number;
}

// Extended correct answer interface with blank_id
interface CorrectAnswer {
  answer_text: string;
  case_sensitive?: boolean;
  exact_match?: boolean;
  blank_id?: number;
}

const QUESTION_TYPES = [
  { value: "SINGLE_CHOICE", label: "Trắc nghiệm 1 đáp án", icon: "⭕" },
  { value: "MULTIPLE_CHOICE", label: "Trắc nghiệm nhiều đáp án", icon: "☑️" },
  { value: "SHORT_ANSWER", label: "Tự luận ngắn", icon: "✍️" },
  { value: "ESSAY", label: "Tự luận dài", icon: "📝" },
  { value: "FILE_UPLOAD", label: "Nộp file", icon: "📎" },
  { value: "FILL_BLANK_TEXT", label: "Điền từ (text)", icon: "⬜" },
  { value: "FILL_BLANK_DROPDOWN", label: "Điền từ (dropdown)", icon: "🔽" },
];

export default function TeacherQuizManagePage() {
  const params = useParams();
  const router = useRouter();
  const quizId = parseInt(params.quizId as string);

  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [showQuestionForm, setShowQuestionForm] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null);
  const [showQuizSettings, setShowQuizSettings] = useState(false);

  // Question form state
  const [questionForm, setQuestionForm] = useState<{
    question_type: string;
    question_text: string;
    question_html: string;
    points: number;
    explanation: string;
    is_required: boolean;
    answer_options: AnswerOption[];
    correct_answers: CorrectAnswer[];
  }>({
    question_type: "SINGLE_CHOICE",
    question_text: "",
    question_html: "",
    points: 10,
    explanation: "",
    is_required: false,
    answer_options: [
      { option_text: "", is_correct: false, order_index: 1 },
      { option_text: "", is_correct: false, order_index: 2 },
    ],
    correct_answers: [],
  });

  // Fill Blank specific state
  const [fillBlankSettings, setFillBlankSettings] = useState<
    FillBlankTextSettings | FillBlankDropdownSettings | null
  >(null);

  // Images for current question
  const [questionImages, setQuestionImages] = useState<QuestionImage[]>([]);

  useEffect(() => {
    loadQuizData();
  }, [quizId]);

  const loadQuizData = async () => {
    try {
      const [quizData, questionsData] = await Promise.all([
        quizService.getQuiz(quizId),
        quizService.listQuestions(quizId),
      ]);
      setQuiz(quizData.data);
      setQuestions(questionsData.data || []);
      setLoading(false);
    } catch (error) {
      console.error("Error loading quiz:", error);
      alert("Không thể tải quiz");
      router.back();
    }
  };

  const loadQuestionImages = async (questionId: number) => {
    try {
      const data = await quizService.listQuestionImages(questionId);
      if (data.data && Array.isArray(data.data)) {
        setQuestionImages(data.data);
      } else {
        setQuestionImages([]);
      }
    } catch (error) {
      console.error("Error loading images:", error);
      setQuestionImages([]);
    }
  };

  const handleCreateQuestion = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      const nextOrderIndex = questions?.length + 1;
      
      const questionData: any = {
        quiz_id: parseInt(String(quizId)),
        question_type: questionForm.question_type,
        question_text: questionForm.question_text.trim(),
        points: parseFloat(String(questionForm.points)),
        order_index: parseInt(String(nextOrderIndex)),
        is_required: questionForm.is_required === true,
      };

      if (questionForm.question_html && questionForm.question_html.trim()) {
        questionData.question_html = questionForm.question_html.trim();
      }
      
      if (questionForm.explanation && questionForm.explanation.trim()) {
        questionData.explanation = questionForm.explanation.trim();
      }

      // === FILL_BLANK_TEXT HANDLING ===
      if (questionForm.question_type === "FILL_BLANK_TEXT") {
        if (!fillBlankSettings || fillBlankSettings.blank_count === 0) {
          alert("Vui lòng thêm ít nhất 1 blank vào câu hỏi (sử dụng {BLANK_1}, {BLANK_2}, ...)");
          return;
        }

        // Validate: mỗi blank phải có ít nhất 1 correct answer
        const blanksWithoutAnswers = fillBlankSettings.blanks.filter(blank => {
          return !questionForm.correct_answers.some(ans => ans.blank_id === blank.blank_id);
        });

        if (blanksWithoutAnswers.length > 0) {
          const blankIds = blanksWithoutAnswers.map(b => `{BLANK_${b.blank_id}}`).join(', ');
          alert(`Các blank sau chưa có đáp án đúng: ${blankIds}`);
          return;
        }

        questionData.settings = fillBlankSettings;
        questionData.correct_answers = questionForm.correct_answers.map(ans => ({
          answer_text: ans.answer_text.trim(),
          blank_id: ans.blank_id,
          case_sensitive: ans.case_sensitive === true,
          exact_match: ans.exact_match === true,
        }));
        questionData.answer_options = [];
      }
      // === FILL_BLANK_DROPDOWN HANDLING ===
      else if (questionForm.question_type === "FILL_BLANK_DROPDOWN") {
        if (!fillBlankSettings || fillBlankSettings.blank_count === 0) {
          alert("Vui lòng thêm ít nhất 1 blank vào câu hỏi (sử dụng {BLANK_1}, {BLANK_2}, ...)");
          return;
        }

        // Validate: mỗi blank phải có ít nhất 2 options và đúng 1 correct
        for (const blank of fillBlankSettings.blanks) {
          const optionsForBlank = questionForm.answer_options.filter(
            opt => opt.blank_id === blank.blank_id
          );

          if (optionsForBlank.length < 2) {
            alert(`Blank {BLANK_${blank.blank_id}} cần ít nhất 2 options`);
            return;
          }

          const correctCount = optionsForBlank.filter(opt => opt.is_correct).length;
          if (correctCount !== 1) {
            alert(`Blank {BLANK_${blank.blank_id}} phải có đúng 1 đáp án đúng (hiện có ${correctCount})`);
            return;
          }
        }

        questionData.settings = fillBlankSettings;
        questionData.answer_options = questionForm.answer_options
          .filter(opt => opt.option_text && opt.option_text.trim())
          .map(opt => ({
            option_text: opt.option_text.trim(),
            is_correct: opt.is_correct === true,
            order_index: opt.order_index,
            blank_id: opt.blank_id,
          }));
        questionData.correct_answers = [];
      }
      // Add answer options for SINGLE_CHOICE, MULTIPLE_CHOICE
      else if (
        questionForm.question_type === "SINGLE_CHOICE" ||
        questionForm.question_type === "MULTIPLE_CHOICE"
      ) {
        const validOptions = questionForm.answer_options.filter(
          (opt) => opt.option_text && opt.option_text.trim()
        );

        if (validOptions?.length < 2) {
          alert("Cần ít nhất 2 đáp án");
          return;
        }

        const hasCorrect = validOptions.some((opt) => opt.is_correct === true);
        if (!hasCorrect) {
          alert("Phải chọn ít nhất 1 đáp án đúng");
          return;
        }

        questionData.answer_options = validOptions.map((opt, index) => ({
          option_text: opt.option_text.trim(),
          is_correct: opt.is_correct === true,
          order_index: index + 1,
        }));
        questionData.correct_answers = [];
      }
      // Add correct answers for SHORT_ANSWER
      else if (questionForm.question_type === "SHORT_ANSWER") {
        if (questionForm.correct_answers?.length > 0) {
          const validAnswers = questionForm.correct_answers.filter(
            (ans) => ans.answer_text && ans.answer_text.trim()
          );
          
          if (validAnswers?.length > 0) {
            questionData.correct_answers = validAnswers.map((ans) => ({
              answer_text: ans.answer_text.trim(),
              case_sensitive: ans.case_sensitive === true,
              exact_match: ans.exact_match === true,
            }));
          } else {
            questionData.correct_answers = [];
          }
        } else {
          questionData.correct_answers = [];
        }
        questionData.answer_options = [];
      }
      // For ESSAY and FILE_UPLOAD
      else {
        questionData.answer_options = [];
        questionData.correct_answers = [];
      }

      if (editingQuestion) {
        const updateData = { ...questionData };
        delete updateData.quiz_id;
        delete updateData.order_index;
        
        await quizService.updateQuestion(editingQuestion.id, updateData);
        alert("Cập nhật câu hỏi thành công!");
      } else {
        const response = await quizService.createQuestion(quizId, questionData);
        alert("Thêm câu hỏi thành công! Bạn có thể thêm hình ảnh ngay.");
        
        // Auto-open edit mode to add images
        if (response.data && response.data.id) {
          const newQuestion = response.data;
          setEditingQuestion(newQuestion);
          setQuestionForm({
            question_type: newQuestion.question_type,
            question_text: newQuestion.question_text,
            question_html: newQuestion.question_html || "",
            points: newQuestion.points,
            explanation: newQuestion.explanation || "",
            is_required: newQuestion.is_required || false,
            answer_options: newQuestion.answer_options || [],
            correct_answers: newQuestion.correct_answers || [],
          });
          setFillBlankSettings(newQuestion.settings || null);
          await loadQuestionImages(newQuestion.id);
          // Keep modal open to add images
          return;
        }
      }

      resetQuestionForm();
      loadQuizData();
    } catch (error: any) {
      console.error("Error saving question:", error);
      const errorMsg = error.response?.data?.message || error.response?.data?.error || "Không thể lưu câu hỏi";
      alert(`Lỗi: ${errorMsg}`);
    }
  };

  const handleDeleteQuestion = async (questionId: number) => {
    if (!confirm("Bạn có chắc muốn xóa câu hỏi này?")) return;

    try {
      await quizService.deleteQuestion(questionId);
      alert("Đã xóa câu hỏi");
      loadQuizData();
    } catch (error) {
      console.error("Error deleting question:", error);
      alert("Không thể xóa câu hỏi");
    }
  };

  const startEditQuestion = (question: Question) => {
    setEditingQuestion(question);
    setQuestionForm({
      question_type: question.question_type,
      question_text: question.question_text,
      question_html: question.question_html || "",
      points: question.points,
      explanation: "",
      is_required: false,
      answer_options: question.answer_options || [],
      correct_answers: question.correct_answers || [],
    });
    setFillBlankSettings(question.settings || null);
    setShowQuestionForm(true);
    loadQuestionImages(question.id);
  };

  const resetQuestionForm = () => {
    setQuestionForm({
      question_type: "SINGLE_CHOICE",
      question_text: "",
      question_html: "",
      points: 10,
      explanation: "",
      is_required: false,
      answer_options: [
        { option_text: "", is_correct: false, order_index: 1 },
        { option_text: "", is_correct: false, order_index: 2 },
      ],
      correct_answers: [],
    });
    setFillBlankSettings(null);
    setEditingQuestion(null);
    setShowQuestionForm(false);
    setQuestionImages([]);
  };

  const addAnswerOption = () => {
    setQuestionForm({
      ...questionForm,
      answer_options: [
        ...questionForm.answer_options,
        {
          option_text: "",
          is_correct: false,
          order_index: questionForm.answer_options.length + 1,
        },
      ],
    });
  };

  const removeAnswerOption = (index: number) => {
    setQuestionForm({
      ...questionForm,
      answer_options: questionForm.answer_options.filter((_, i) => i !== index),
    });
  };

  const updateAnswerOption = (index: number, field: string, value: any) => {
    const newOptions = questionForm.answer_options.map((opt, i) => {
      if (i === index) {
        // For single choice, if setting is_correct to true, unset others
        if (field === "is_correct" && value === true && questionForm.question_type === "SINGLE_CHOICE") {
          return { ...opt, is_correct: true };
        }
        return { ...opt, [field]: value };
      }
      // Unset other options if single choice
      if (field === "is_correct" && value === true && questionForm.question_type === "SINGLE_CHOICE") {
        return { ...opt, is_correct: false };
      }
      return opt;
    });
    
    setQuestionForm({
      ...questionForm,
      answer_options: newOptions,
    });
  };

  const addCorrectAnswer = () => {
    setQuestionForm({
      ...questionForm,
      correct_answers: [
        ...questionForm.correct_answers,
        {
          answer_text: "",
          case_sensitive: false,
          exact_match: true,
        },
      ],
    });
  };

  const removeCorrectAnswer = (index: number) => {
    setQuestionForm({
      ...questionForm,
      correct_answers: questionForm.correct_answers.filter((_, i) => i !== index),
    });
  };

  const updateCorrectAnswer = (index: number, field: string, value: any) => {
    const newAnswers = questionForm.correct_answers.map((ans, i) =>
      i === index ? { ...ans, [field]: value } : ans
    );
    setQuestionForm({
      ...questionForm,
      correct_answers: newAnswers,
    });
  };

  const handleUpdateQuizSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quiz) return;

    try {
      await quizService.updateQuiz(quiz.id, {
        time_limit_minutes: quiz.time_limit_minutes,
        max_attempts: quiz.max_attempts,
        passing_score: quiz.passing_score,
        total_points: quiz.total_points,
        auto_grade: quiz.auto_grade,
        show_results_immediately: quiz.show_results_immediately,
        show_correct_answers: quiz.show_correct_answers,
        allow_review: quiz.allow_review,
        is_published: quiz.is_published,
      });
      alert("Đã cập nhật cài đặt quiz");
      setShowQuizSettings(false);
      loadQuizData();
    } catch (error) {
      console.error("Error updating quiz:", error);
      alert("Không thể cập nhật cài đặt");
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6 text-center">
        <p>Đang tải...</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <Button onClick={() => router.back()} variant="outline" className="mb-4">
          ← Quay lại
        </Button>
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{quiz?.title}</h1>
            <p className="text-gray-600 mt-2">{quiz?.description}</p>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={() => setShowQuizSettings(true)}
              variant="outline"
              className="px-4 py-2"
            >
              ⚙️ Cài đặt Quiz
            </Button>
            <Button
              onClick={() => router.push(`/lms/teacher/quiz/${quizId}/grading`)}
              className="px-4 py-2 bg-green-600 text-white hover:bg-green-700"
            >
              ✓ Chấm bài
            </Button>
          </div>
        </div>
      </div>

      {/* Quiz Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-gray-600">Tổng câu hỏi</p>
          <p className="text-2xl font-bold text-blue-700">{questions?.length}</p>
        </div>
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
          <p className="text-sm text-gray-600">Tổng điểm</p>
          <p className="text-2xl font-bold text-purple-700">{quiz?.total_points}</p>
        </div>
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
          <p className="text-sm text-gray-600">Thời gian</p>
          <p className="text-2xl font-bold text-orange-700">
            {quiz?.time_limit_minutes || "∞"} {quiz?.time_limit_minutes ? "phút" : ""}
          </p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-sm text-gray-600">Trạng thái</p>
          <p className="text-2xl font-bold text-green-700">
            {quiz?.is_published ? "✓ Published" : "📝 Draft"}
          </p>
        </div>
      </div>

      {/* Questions List */}
      <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold">Danh sách câu hỏi</h2>
          <Button
            onClick={() => setShowQuestionForm(true)}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
          >
            + Thêm câu hỏi
          </Button>
        </div>

        {questions?.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">📝</div>
            <h3 className="text-xl font-bold text-gray-900 mb-2">
              Chưa có câu hỏi nào
            </h3>
            <p className="text-gray-600 mb-4">
              Thêm câu hỏi đầu tiên để học sinh có thể làm quiz
            </p>
            <Button
              onClick={() => setShowQuestionForm(true)}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
            >
              + Thêm câu hỏi đầu tiên
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {questions.map((question, index) => {
              const images = question.settings?.images || [];
              return (
                <div
                  key={question.id}
                  className="border rounded-lg p-4 hover:bg-gray-50 transition"
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded text-sm font-medium">
                          Câu {index + 1}
                        </span>
                        <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded text-sm">
                          {
                            QUESTION_TYPES.find(
                              (t) => t.value === question.question_type
                            )?.icon
                          }{" "}
                          {
                            QUESTION_TYPES.find(
                              (t) => t.value === question.question_type
                            )?.label
                          }
                        </span>
                        <span className="px-3 py-1 bg-purple-100 text-purple-700 rounded text-sm font-semibold">
                          {question.points} điểm
                        </span>
                        {images?.length > 0 && (
                          <span className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm font-medium">
                            🖼️ {images?.length} ảnh
                          </span>
                        )}
                      </div>
                      <p className="text-gray-900 font-medium mb-2">
                        {question.question_text}
                      </p>

                      {/* Question Images Preview */}
                      {images?.length > 0 && (
                        <div className="mt-3 flex gap-2 flex-wrap">
                          {images.slice(0, 4).map((img: QuestionImage) => (
                            <img
                              key={img.id}
                              src={img.url}
                              alt={img.alt_text || img.file_name}
                              className="w-24 h-24 object-cover rounded-lg border-2 border-gray-200 hover:border-blue-400 transition-all cursor-pointer"
                              title={img.caption || img.file_name}
                            />
                          ))}
                          {images?.length > 4 && (
                            <div className="w-24 h-24 bg-gradient-to-br from-gray-100 to-gray-200 rounded-lg flex items-center justify-center border-2 border-gray-200">
                              <span className="text-sm font-bold text-gray-600">
                                +{images?.length - 4}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Answer options preview */}
                      {question.answer_options?.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {question.answer_options.map((opt: any, idx: number) => (
                            <div
                              key={idx}
                              className={`text-sm px-3 py-1 rounded ${
                                opt.is_correct
                                  ? "bg-green-50 text-green-700 font-medium"
                                  : "text-gray-600"
                              }`}
                            >
                              {opt.is_correct ? "✓" : "○"} {opt.option_text}
                              {opt.blank_id && (
                                <span className="ml-2 text-xs text-blue-600">
                                  [BLANK_{opt.blank_id}]
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Correct answers preview for text-based questions */}
                      {question.correct_answers?.length > 0 && (
                        <div className="mt-2 space-y-1">
                          <p className="text-xs font-medium text-gray-600">Đáp án đúng:</p>
                          {question.correct_answers.map((ans: any, idx: number) => (
                            <div
                              key={idx}
                              className="text-sm px-3 py-1 rounded bg-green-50 text-green-700"
                            >
                              ✓ {ans.answer_text}
                              {ans.blank_id && (
                                <span className="ml-2 text-xs text-blue-600">
                                  [BLANK_{ans.blank_id}]
                                </span>
                              )}
                              {ans.case_sensitive && (
                                <span className="ml-2 text-xs">(Aa)</span>
                              )}
                              {ans.exact_match && (
                                <span className="ml-2 text-xs">(=)</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="flex gap-2 ml-4">
                      <Button
                        onClick={() => startEditQuestion(question)}
                        variant="outline"
                        className="px-4 py-2"
                      >
                        ✏️ Sửa
                      </Button>
                      <Button
                        onClick={() => handleDeleteQuestion(question.id)}
                        variant="outline"
                        className="px-4 py-2 text-red-600 border-red-300 hover:bg-red-50"
                      >
                        🗑️ Xóa
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Question Form Modal */}
      {showQuestionForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
          <div className="bg-white rounded-xl max-w-4xl w-full my-8">
            <div className="p-6 border-b sticky top-0 bg-white z-10 rounded-t-xl">
              <h2 className="text-xl font-bold">
                {editingQuestion ? "Chỉnh sửa câu hỏi" : "Thêm câu hỏi mới"}
              </h2>
              {editingQuestion && (
                <p className="text-sm text-gray-600 mt-1">
                  ID: {editingQuestion.id} • {questionImages?.length} hình ảnh
                </p>
              )}
            </div>

            <form onSubmit={handleCreateQuestion} className="p-6 max-h-[75vh] overflow-y-auto">
              <div className="space-y-6">
                {/* Question Type */}
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Loại câu hỏi *
                  </label>
                  <select
                    value={questionForm.question_type}
                    onChange={(e) => {
                      const newType = e.target.value;
                      setQuestionForm({
                        ...questionForm,
                        question_type: newType,
                      });
                      // Reset Fill Blank state when changing type
                      setFillBlankSettings(null);
                    }}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    required
                    disabled={!!editingQuestion}
                  >
                    {QUESTION_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.icon} {type.label}
                      </option>
                    ))}
                  </select>
                  {editingQuestion && (
                    <p className="text-xs text-gray-500 mt-1">
                      Không thể thay đổi loại câu hỏi khi sửa
                    </p>
                  )}
                </div>

                {/* === FILL_BLANK_TEXT EDITOR === */}
                {questionForm.question_type === "FILL_BLANK_TEXT" && (
                  <FillBlankTextEditor
                    questionText={questionForm.question_text}
                    settings={fillBlankSettings as FillBlankTextSettings || { blank_count: 0, blanks: [] }}
                    correctAnswers={questionForm.correct_answers as FillBlankTextCorrectAnswer[]}
                    onChange={(text, settings, answers) => {
                      setQuestionForm({
                        ...questionForm,
                        question_text: text,
                        correct_answers: answers,
                      });
                      setFillBlankSettings(settings);
                    }}
                  />
                )}

                {/* === FILL_BLANK_DROPDOWN EDITOR === */}
                {questionForm.question_type === "FILL_BLANK_DROPDOWN" && (
                  <FillBlankDropdownEditor
                    questionText={questionForm.question_text}
                    settings={fillBlankSettings as FillBlankDropdownSettings || { blank_count: 0, blanks: [] }}
                    options={questionForm.answer_options as FillBlankDropdownOption[]}
                    onChange={(text, settings, options) => {
                      setQuestionForm({
                        ...questionForm,
                        question_text: text,
                        answer_options: options,
                      });
                      setFillBlankSettings(settings);
                    }}
                  />
                )}

                {/* === REGULAR QUESTION TEXT (for non-fill-blank types) === */}
                {questionForm.question_type !== "FILL_BLANK_TEXT" &&
                 questionForm.question_type !== "FILL_BLANK_DROPDOWN" && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Câu hỏi *
                    </label>
                    <textarea
                      value={questionForm.question_text}
                      onChange={(e) =>
                        setQuestionForm({
                          ...questionForm,
                          question_text: e.target.value,
                        })
                      }
                      className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                      rows={3}
                      placeholder="Nhập nội dung câu hỏi..."
                      required
                    />
                  </div>
                )}

                {/* Question Images - Only show if question is saved */}
                {editingQuestion && (
                  <div className="border-t pt-6">
                    <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                      <span className="text-2xl">🖼️</span>
                      Hình ảnh minh họa
                    </h3>
                    <QuestionImageUploader
                      questionId={editingQuestion.id}
                      images={questionImages}
                      onImagesUpdate={() => {
                        loadQuestionImages(editingQuestion.id);
                        loadQuizData();
                      }}
                    />
                  </div>
                )}

                {/* Points and Required */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Điểm *</label>
                    <input
                      type="number"
                      value={questionForm.points}
                      onChange={(e) =>
                        setQuestionForm({
                          ...questionForm,
                          points: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                      min="0"
                      step="0.5"
                      required
                    />
                  </div>

                  <div className="flex items-center pt-6">
                    <label className="flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={questionForm.is_required}
                        onChange={(e) =>
                          setQuestionForm({
                            ...questionForm,
                            is_required: e.target.checked,
                          })
                        }
                        className="w-4 h-4 mr-2"
                      />
                      <span className="text-sm font-medium">Câu hỏi bắt buộc</span>
                    </label>
                  </div>
                </div>

                {/* Answer Options for SINGLE_CHOICE and MULTIPLE_CHOICE */}
                {(questionForm.question_type === "SINGLE_CHOICE" ||
                  questionForm.question_type === "MULTIPLE_CHOICE") && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Đáp án *
                    </label>
                    <div className="space-y-2">
                      {questionForm.answer_options.map((option, index) => (
                        <div key={index} className="flex gap-2">
                          <input
                            type={
                              questionForm.question_type === "SINGLE_CHOICE"
                                ? "radio"
                                : "checkbox"
                            }
                            checked={option.is_correct}
                            onChange={(e) =>
                              updateAnswerOption(
                                index,
                                "is_correct",
                                e.target.checked
                              )
                            }
                            className="mt-3"
                          />
                          <input
                            type="text"
                            value={option.option_text}
                            onChange={(e) =>
                              updateAnswerOption(
                                index,
                                "option_text",
                                e.target.value
                              )
                            }
                            className="flex-1 px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                            placeholder={`Đáp án ${index + 1}`}
                            required
                          />
                          {questionForm.answer_options?.length > 2 && (
                            <Button
                              type="button"
                              onClick={() => removeAnswerOption(index)}
                              variant="outline"
                              className="px-4 py-2 text-red-600"
                            >
                              ✕
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                    <Button
                      type="button"
                      onClick={addAnswerOption}
                      variant="outline"
                      className="mt-2 w-full"
                    >
                      + Thêm đáp án
                    </Button>
                  </div>
                )}

                {/* Correct Answers for SHORT_ANSWER */}
                {questionForm.question_type === "SHORT_ANSWER" && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Đáp án đúng (tùy chọn)
                    </label>
                    <div className="space-y-2">
                      {questionForm.correct_answers.map((answer, index) => (
                        <div key={index} className="space-y-2 p-3 border rounded-lg">
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={answer.answer_text}
                              onChange={(e) =>
                                updateCorrectAnswer(index, "answer_text", e.target.value)
                              }
                              className="flex-1 px-4 py-2 border rounded-lg"
                              placeholder="Đáp án đúng..."
                            />
                            {questionForm.correct_answers?.length > 1 && (
                              <Button
                                type="button"
                                onClick={() => removeCorrectAnswer(index)}
                                variant="outline"
                                className="px-4 py-2 text-red-600"
                              >
                                ✕
                              </Button>
                            )}
                          </div>
                          <div className="flex gap-4 text-sm">
                            <label className="flex items-center">
                              <input
                                type="checkbox"
                                checked={answer.case_sensitive}
                                onChange={(e) =>
                                  updateCorrectAnswer(index, "case_sensitive", e.target.checked)
                                }
                                className="mr-2"
                              />
                              Phân biệt hoa/thường
                            </label>
                            <label className="flex items-center">
                              <input
                                type="checkbox"
                                checked={answer.exact_match}
                                onChange={(e) =>
                                  updateCorrectAnswer(index, "exact_match", e.target.checked)
                                }
                                className="mr-2"
                              />
                              Khớp chính xác
                            </label>
                          </div>
                        </div>
                      ))}
                    </div>
                    <Button
                      type="button"
                      onClick={addCorrectAnswer}
                      variant="outline"
                      className="mt-2 w-full"
                    >
                      + Thêm đáp án đúng
                    </Button>
                  </div>
                )}

                {/* Explanation */}
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Giải thích (tùy chọn)
                  </label>
                  <textarea
                    value={questionForm.explanation}
                    onChange={(e) =>
                      setQuestionForm({
                        ...questionForm,
                        explanation: e.target.value,
                      })
                    }
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    rows={2}
                    placeholder="Giải thích đáp án đúng..."
                  />
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3 mt-6 pt-4 border-t">
                <Button
                  type="submit"
                  className="flex-1 bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
                >
                  {editingQuestion ? "💾 Cập nhật" : "✅ Lưu & Thêm ảnh"}
                </Button>
                <Button
                  type="button"
                  onClick={resetQuestionForm}
                  variant="outline"
                  className="px-6 py-2"
                >
                  {editingQuestion ? "Đóng" : "Hủy"}
                </Button>
              </div>
              
              {!editingQuestion && (
                <p className="text-sm text-amber-600 mt-3 text-center bg-amber-50 p-3 rounded-lg border border-amber-200">
                  💡 Sau khi lưu câu hỏi, form sẽ tự động chuyển sang chế độ chỉnh sửa để bạn thêm hình ảnh
                </p>
              )}
            </form>
          </div>
        </div>
      )}

      {/* Quiz Settings Modal */}
      {showQuizSettings && quiz && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b sticky top-0 bg-white z-10">
              <h2 className="text-xl font-bold">Cài đặt Quiz</h2>
            </div>

            <form onSubmit={handleUpdateQuizSettings} className="p-6">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Thời gian (phút)
                    </label>
                    <input
                      type="number"
                      value={quiz.time_limit_minutes || ""}
                      onChange={(e) =>
                        setQuiz({
                          ...quiz,
                          time_limit_minutes: e.target.value
                            ? parseInt(e.target.value)
                            : null,
                        })
                      }
                      className="w-full px-4 py-2 border rounded-lg"
                      min="1"
                      placeholder="Không giới hạn"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Số lần làm tối đa
                    </label>
                    <input
                      type="number"
                      value={quiz.max_attempts || ""}
                      onChange={(e) =>
                        setQuiz({
                          ...quiz,
                          max_attempts: e.target.value
                            ? parseInt(e.target.value)
                            : null,
                        })
                      }
                      className="w-full px-4 py-2 border rounded-lg"
                      min="1"
                      placeholder="Không giới hạn"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Điểm đạt (%)
                    </label>
                    <input
                      type="number"
                      value={quiz.passing_score || ""}
                      onChange={(e) =>
                        setQuiz({
                          ...quiz,
                          passing_score: e.target.value
                            ? parseFloat(e.target.value)
                            : null,
                        })
                      }
                      className="w-full px-4 py-2 border rounded-lg"
                      min="0"
                      max="100"
                      step="0.1"
                      placeholder="VD: 70"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Tổng điểm
                    </label>
                    <input
                      type="number"
                      value={quiz.total_points}
                      onChange={(e) =>
                        setQuiz({
                          ...quiz,
                          total_points: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full px-4 py-2 border rounded-lg"
                      min="0"
                      step="0.5"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2 pt-4 border-t">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={quiz.auto_grade}
                      onChange={(e) =>
                        setQuiz({ ...quiz, auto_grade: e.target.checked })
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm">Tự động chấm điểm</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={quiz.show_results_immediately}
                      onChange={(e) =>
                        setQuiz({
                          ...quiz,
                          show_results_immediately: e.target.checked,
                        })
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm">Hiển thị kết quả ngay</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={quiz.show_correct_answers}
                      onChange={(e) =>
                        setQuiz({
                          ...quiz,
                          show_correct_answers: e.target.checked,
                        })
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm">Hiển thị đáp án đúng</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={quiz.allow_review}
                      onChange={(e) =>
                        setQuiz({ ...quiz, allow_review: e.target.checked })
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm">Cho phép xem lại bài làm</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer p-3 bg-green-50 border border-green-200 rounded-lg">
                    <input
                      type="checkbox"
                      checked={quiz.is_published}
                      onChange={(e) =>
                        setQuiz({ ...quiz, is_published: e.target.checked })
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm font-semibold text-green-700">
                      ✓ Publish quiz (học sinh có thể làm)
                    </span>
                  </label>
                </div>
              </div>

              <div className="flex gap-3 mt-6 pt-4 border-t">
                <Button
                  type="submit"
                  className="flex-1 bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
                >
                  Lưu cài đặt
                </Button>
                <Button
                  type="button"
                  onClick={() => setShowQuizSettings(false)}
                  variant="outline"
                  className="px-6 py-2"
                >
                  Hủy
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}