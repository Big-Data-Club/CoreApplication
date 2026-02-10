/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import quizService from "@/services/quizService";
import { Button } from "@/components/ui/button";

interface QuestionImage {
  id: string;
  url: string;
  file_name: string;
  caption?: string;
  alt_text?: string;
  display_width?: string;
  position?: string;
}

interface Question {
  id: number;
  question_type: string;
  question_text: string;
  question_html?: string;
  points: number;
  order_index: number;
  settings?: {
    images?: QuestionImage[];
  };
  answer_options?: any[];
  is_required: boolean;
}

interface Quiz {
  id: number;
  title: string;
  description: string;
  instructions: string;
  time_limit_minutes: number | null;
  total_points: number;
  passing_score: number | null;
  shuffle_questions: boolean;
  shuffle_answers: boolean;
}

interface QuizAttempt {
  id: number;
  quiz_id: number;
  started_at: string;
  time_spent_seconds: number;
}

export default function StudentQuizTakingPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = parseInt(params.quizId as string);

  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [attempt, setAttempt] = useState<QuizAttempt | null>(null);
  const [answers, setAnswers] = useState<{ [key: number]: any }>({});
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number | null>(null);
  const [showImageModal, setShowImageModal] = useState<string | null>(null);

  useEffect(() => {
    startQuiz();
  }, [quizId]);

  // Timer countdown
  useEffect(() => {
    if (!quiz?.time_limit_minutes || timeLeft === null) return;

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev === null || prev <= 0) {
          handleAutoSubmit();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [quiz, timeLeft]);

  const startQuiz = async () => {
    try {
      const [quizData, attemptData] = await Promise.all([
        quizService.getQuiz(quizId),
        quizService.startQuizAttempt(quizId),
      ]);

      const quizInfo = quizData.data;
      const attemptInfo = attemptData.data;

      setQuiz(quizInfo);
      setAttempt(attemptInfo);

      // Load questions
      const questionsData = await quizService.listQuestions(quizId);
      let questionList = questionsData.data || [];

      // Shuffle questions if needed
      if (quizInfo.shuffle_questions) {
        questionList = shuffleArray(questionList);
      }

      // Shuffle answers if needed
      if (quizInfo.shuffle_answers) {
        questionList = questionList.map((q: Question) => ({
          ...q,
          answer_options: q.answer_options ? shuffleArray(q.answer_options) : [],
        }));
      }

      setQuestions(questionList);

      // Set timer
      if (quizInfo.time_limit_minutes) {
        setTimeLeft(quizInfo.time_limit_minutes * 60);
      }

      setLoading(false);
    } catch (error: any) {
      console.error("Error starting quiz:", error);
      alert(error.response?.data?.message || "Không thể bắt đầu quiz");
      router.back();
    }
  };

  const shuffleArray = (array: any[]) => {
    const newArray = [...array];
    for (let i = newArray.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [newArray[i], newArray[j]] = [newArray[j], newArray[i]];
    }
    return newArray;
  };

  const handleAnswerChange = async (questionId: number, answerData: any) => {
    setAnswers({ ...answers, [questionId]: answerData });

    // Auto-save answer to backend
    if (attempt) {
      try {
        await quizService.submitAnswer(attempt.id, {
          attempt_id: attempt.id,
          question_id: questionId,
          answer_data: answerData,
        });
      } catch (error) {
        console.error("Error saving answer:", error);
      }
    }
  };

  const handleAutoSubmit = async () => {
    if (submitting) return;
    alert("Hết giờ! Quiz sẽ được tự động nộp.");
    await handleSubmit();
  };

  const handleSubmit = async () => {
    if (!attempt) return;

    // Check required questions
    const unansweredRequired = questions.filter(
      (q) => q.is_required && !answers[q.id]
    );

    if (unansweredRequired.length > 0) {
      if (!confirm(`Còn ${unansweredRequired.length} câu hỏi bắt buộc chưa trả lời. Bạn có chắc muốn nộp bài?`)) {
        return;
      }
    }

    if (!confirm("Bạn có chắc muốn nộp bài? Bạn sẽ không thể chỉnh sửa sau khi nộp.")) {
      return;
    }

    try {
      setSubmitting(true);
      const result = await quizService.submitQuiz(attempt.id);
      alert("Nộp bài thành công!");
      router.push(`/lms/student/quiz/${quizId}/result/${attempt.id}`);
    } catch (error: any) {
      console.error("Error submitting quiz:", error);
      alert(error.response?.data?.message || "Không thể nộp bài");
      setSubmitting(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const renderQuestionImages = (images: QuestionImage[] | undefined, position: string = "above_question") => {
    if (!images || images.length === 0) return null;

    const positionImages = images.filter(img => (img.position || "above_question") === position);
    if (positionImages.length === 0) return null;

    return (
      <div className="my-4 space-y-3">
        {positionImages.map((image) => (
          <div key={image.id} className="relative group">
            <div className="relative rounded-lg overflow-hidden border-2 border-gray-200 hover:border-blue-400 transition-all">
              <img
                src={image.url}
                alt={image.alt_text || image.file_name}
                className="w-full cursor-pointer hover:opacity-95 transition-opacity"
                style={{ maxWidth: image.display_width || "100%" }}
                onClick={() => setShowImageModal(image.url)}
              />
              {image.caption && (
                <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-70 text-white text-sm p-2">
                  {image.caption}
                </div>
              )}
            </div>
            <button
              onClick={() => setShowImageModal(image.url)}
              className="absolute top-2 right-2 bg-white bg-opacity-90 hover:bg-opacity-100 rounded-full p-2 shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
              title="Xem ảnh lớn"
            >
              🔍
            </button>
          </div>
        ))}
      </div>
    );
  };

  const renderQuestion = (question: Question) => {
    const questionImages = question.settings?.images || [];

    return (
      <div className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
        {/* Question Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-4">
              <span className="px-4 py-2 bg-blue-100 text-blue-700 rounded-lg font-bold text-lg">
                Câu {currentQuestion + 1}/{questions.length}
              </span>
              <span className="px-4 py-2 bg-purple-100 text-purple-700 rounded-lg font-semibold">
                {question.points} điểm
              </span>
              {question.is_required && (
                <span className="px-4 py-2 bg-red-100 text-red-700 rounded-lg text-sm font-medium">
                  * Bắt buộc
                </span>
              )}
              {questionImages.length > 0 && (
                <span className="px-4 py-2 bg-green-100 text-green-700 rounded-lg text-sm font-medium">
                  🖼️ {questionImages.length} ảnh
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Images ABOVE question */}
        {renderQuestionImages(questionImages, "above_question")}

        {/* Question Text */}
        <div className="mb-6">
          <h2 className="text-xl font-bold text-gray-900 leading-relaxed">
            {question.question_text}
          </h2>
          {question.question_html && (
            <div
              className="mt-3 text-gray-700 prose max-w-none"
              dangerouslySetInnerHTML={{ __html: question.question_html }}
            />
          )}
        </div>

        {/* Images BELOW question */}
        {renderQuestionImages(questionImages, "below_question")}

        {/* Answer Input */}
        <div className="mt-6">
          {question.question_type === "SINGLE_CHOICE" && (
            <div className="space-y-3">
              {question.answer_options?.map((option, idx) => (
                <label
                  key={idx}
                  className={`flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all ${
                    answers[question.id]?.selected_option_id === option.id
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-300 hover:border-blue-300 hover:bg-gray-50"
                  }`}
                >
                  <input
                    type="radio"
                    name={`question_${question.id}`}
                    checked={answers[question.id]?.selected_option_id === option.id}
                    onChange={() =>
                      handleAnswerChange(question.id, {
                        selected_option_id: option.id,
                        type: "single_choice",
                      })
                    }
                    className="mt-1 w-5 h-5"
                  />
                  <span className="text-gray-900 flex-1">{option.option_text}</span>
                </label>
              ))}
            </div>
          )}

          {question.question_type === "MULTIPLE_CHOICE" && (
            <div className="space-y-3">
              {question.answer_options?.map((option, idx) => (
                <label
                  key={idx}
                  className={`flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all ${
                    answers[question.id]?.selected_option_ids?.includes(option.id)
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-300 hover:border-blue-300 hover:bg-gray-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={answers[question.id]?.selected_option_ids?.includes(option.id) || false}
                    onChange={(e) => {
                      const currentIds = answers[question.id]?.selected_option_ids || [];
                      const newIds = e.target.checked
                        ? [...currentIds, option.id]
                        : currentIds.filter((id: number) => id !== option.id);
                      handleAnswerChange(question.id, {
                        selected_option_ids: newIds,
                        type: "multiple_choice",
                      });
                    }}
                    className="mt-1 w-5 h-5"
                  />
                  <span className="text-gray-900 flex-1">{option.option_text}</span>
                </label>
              ))}
            </div>
          )}

          {question.question_type === "SHORT_ANSWER" && (
            <input
              type="text"
              value={answers[question.id]?.answer_text || ""}
              onChange={(e) =>
                handleAnswerChange(question.id, {
                  answer_text: e.target.value,
                  type: "short_answer",
                })
              }
              className="w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
              placeholder="Nhập câu trả lời của bạn..."
            />
          )}

          {question.question_type === "ESSAY" && (
            <textarea
              value={answers[question.id]?.answer_text || ""}
              onChange={(e) =>
                handleAnswerChange(question.id, {
                  answer_text: e.target.value,
                  type: "essay",
                })
              }
              className="w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
              rows={8}
              placeholder="Nhập bài luận của bạn..."
            />
          )}
        </div>

        {/* Images AT BOTTOM */}
        {renderQuestionImages(questionImages, "bottom")}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Đang tải quiz...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-transparent py-8">
      <div className="max-w-4xl mx-auto px-4">
        {/* Header */}
        <div className="bg-white rounded-xl shadow-lg p-6 mb-6">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{quiz?.title}</h1>
              <p className="text-gray-600 mt-2">{quiz?.description}</p>
            </div>
            {timeLeft !== null && (
              <div className={`px-6 py-3 rounded-lg font-bold text-xl ${
                timeLeft < 300 ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"
              }`}>
                ⏱️ {formatTime(timeLeft)}
              </div>
            )}
          </div>

          {/* Progress Bar */}
          <div className="mt-6">
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>Tiến độ</span>
              <span>{Object.keys(answers).length}/{questions.length} câu đã trả lời</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                style={{
                  width: `${(Object.keys(answers).length / questions.length) * 100}%`,
                }}
              />
            </div>
          </div>
        </div>

        {/* Question */}
        {questions.length > 0 && renderQuestion(questions[currentQuestion])}

        {/* Navigation */}
        <div className="flex justify-between items-center mt-6 gap-4">
          <Button
            onClick={() => setCurrentQuestion(Math.max(0, currentQuestion - 1))}
            disabled={currentQuestion === 0}
            className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            ← Câu trước
          </Button>

          <div className="flex gap-2 flex-wrap justify-center">
            {questions.map((_, idx) => (
              <button
                key={idx}
                onClick={() => setCurrentQuestion(idx)}
                className={`w-10 h-10 rounded-lg font-semibold transition-all ${
                  idx === currentQuestion
                    ? "bg-blue-600 text-white scale-110"
                    : answers[questions[idx].id]
                    ? "bg-green-100 text-green-700 border-2 border-green-500"
                    : "bg-gray-100 text-gray-700 border-2 border-gray-300"
                }`}
              >
                {idx + 1}
              </button>
            ))}
          </div>

          {currentQuestion < questions.length - 1 ? (
            <Button
              onClick={() => setCurrentQuestion(currentQuestion + 1)}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Câu sau →
            </Button>
          ) : (
            <Button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {submitting ? "Đang nộp..." : "✓ Nộp bài"}
            </Button>
          )}
        </div>

        {/* Instructions */}
        {quiz?.instructions && (
          <div className="mt-6 bg-yellow-50 border-2 border-yellow-200 rounded-lg p-4">
            <p className="text-sm text-yellow-800">
              <strong>💡 Lưu ý:</strong> {quiz.instructions}
            </p>
          </div>
        )}
      </div>

      {/* Image Modal */}
      {showImageModal && (
        <div
          className="fixed inset-0 bg-black bg-opacity-95 z-50 flex items-center justify-center p-4"
          onClick={() => setShowImageModal(null)}
        >
          <div className="relative max-w-7xl max-h-full">
            <button
              onClick={() => setShowImageModal(null)}
              className="absolute -top-14 right-0 bg-white hover:bg-gray-100 text-gray-800 px-4 py-2 rounded-lg shadow-lg font-semibold"
            >
              ✕ Đóng (ESC)
            </button>
            <img
              src={showImageModal}
              alt="Preview"
              className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </div>
  );
}