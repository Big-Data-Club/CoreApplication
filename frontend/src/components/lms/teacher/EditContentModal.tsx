"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import FileUpload from "@/components/lms/teacher/FileUpload";
import QuizSettingsForm, { QuizSettings } from "./QuizSettingsForm";
import lmsService from "@/services/lmsService";
import quizService from "@/services/quizService";
import { Content, FileInfo } from "@/types";
import { useRouter } from "next/navigation";

interface EditContentModalProps {
  content: Content;
  onClose: () => void;
  onSuccess: () => void;
}

export default function EditContentModal({
  content,
  onClose,
  onSuccess,
}: EditContentModalProps) {
  const [formData, setFormData] = useState({
    title: content.title,
    description: content.description,
    order_index: content.order_index,
    is_mandatory: content.is_mandatory,
    metadata: content.metadata || {},
  });

  const [quizSettings, setQuizSettings] = useState<QuizSettings | null>(null);
  const [quizId, setQuizId] = useState<number | null>(null);
  const [loadingQuiz, setLoadingQuiz] = useState(false);

  const [loading, setLoading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<FileInfo | null>(null);
  const [textContent, setTextContent] = useState(
    content.metadata?.content || ""
  );
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [removeFileConfirm, setRemoveFileConfirm] = useState(false);
  const router = useRouter();

  // Load quiz settings if content type is QUIZ
  useEffect(() => {
    if (content.type === "QUIZ") {
      loadQuizSettings();
    }
  }, [content.id, content.type]);

  const loadQuizSettings = async () => {
    try {
      setLoadingQuiz(true);
      const response = await quizService.getQuizByContentId(content.id);
      
      if (response.data) {
        const quiz = response.data;
        setQuizId(quiz.id);
        
        // Convert quiz data to QuizSettings format
        setQuizSettings({
          title: quiz.title,
          description: quiz.description || "",
          instructions: quiz.instructions || "",
          time_limit_minutes: quiz.time_limit_minutes || undefined,
          available_from: quiz.available_from 
            ? new Date(quiz.available_from).toISOString().slice(0, 16) 
            : undefined,
          available_until: quiz.available_until 
            ? new Date(quiz.available_until).toISOString().slice(0, 16) 
            : undefined,
          max_attempts: quiz.max_attempts || undefined,
          shuffle_questions: quiz.shuffle_questions || false,
          shuffle_answers: quiz.shuffle_answers || false,
          passing_score: quiz.passing_score || undefined,
          total_points: quiz.total_points || 100,
          auto_grade: quiz.auto_grade ?? true,
          show_results_immediately: quiz.show_results_immediately ?? true,
          show_correct_answers: quiz.show_correct_answers ?? true,
          allow_review: quiz.allow_review ?? true,
          show_feedback: quiz.show_feedback ?? true,
        });
      }
    } catch (error: any) {
      console.error("Error loading quiz:", error);
      // Quiz might not exist yet, that's ok
      setQuizSettings({
        title: content.title,
        description: content.description || "",
        instructions: "",
        time_limit_minutes: undefined,
        available_from: undefined,
        available_until: undefined,
        max_attempts: undefined,
        shuffle_questions: false,
        shuffle_answers: false,
        passing_score: undefined,
        total_points: 100,
        auto_grade: true,
        show_results_immediately: true,
        show_correct_answers: true,
        allow_review: true,
        show_feedback: true,
      });
    } finally {
      setLoadingQuiz(false);
    }
  };

  const getContentTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      TEXT: "Văn bản",
      VIDEO: "Video",
      DOCUMENT: "Tài liệu",
      IMAGE: "Hình ảnh",
      QUIZ: "Quiz",
      FORUM: "Diễn đàn",
      ANNOUNCEMENT: "Thông báo",
    };
    return labels[type] || type;
  };

  const getFileUploadType = (contentType: string): "video" | "document" | "image" => {
    switch (contentType) {
      case "VIDEO":
        return "video";
      case "IMAGE":
        return "image";
      case "DOCUMENT":
        return "document";
      default:
        return "document";
    }
  };

  const handleFileUploaded = (fileInfo: FileInfo) => {
    setUploadedFile(fileInfo);
    setFormData({
      ...formData,
      metadata: {
        ...formData.metadata,
        file_path: fileInfo.file_path,
        file_name: fileInfo.file_name,
        file_size: fileInfo.file_size,
        file_id: fileInfo.file_id,
      },
    });
    setShowFileUpload(false);
  };

  const removeCurrentFile = () => {
    setUploadedFile(null);
    setFormData({
      ...formData,
      metadata: {
        ...formData.metadata,
        file_path: undefined,
        file_name: undefined,
        file_size: undefined,
        file_id: undefined,
      },
    });
    setRemoveFileConfirm(false);
  };

  const handleTitleChange = (title: string) => {
    setFormData({ ...formData, title });
    if (content.type === "QUIZ" && quizSettings) {
      setQuizSettings({ ...quizSettings, title });
    }
  };

  const handleDescriptionChange = (description: string) => {
    setFormData({ ...formData, description });
    if (content.type === "QUIZ" && quizSettings) {
      setQuizSettings({ ...quizSettings, description });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const metadata = { ...formData.metadata };

    if (content.type === "TEXT") {
      metadata.content = textContent;
    } else if (content.type === "QUIZ" && quizSettings) {
      metadata.quiz_settings = quizSettings;
    }

    try {
      setLoading(true);
      
      // Update content
      await lmsService.updateContent(content.id, {
        ...formData,
        metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
      });

      // If it's a quiz, update or create quiz record
      if (content.type === "QUIZ" && quizSettings) {
        try {
          if (quizId) {
            // Update existing quiz
            await quizService.updateQuiz(quizId, quizSettings);
          } else {
            // Create new quiz if it doesn't exist
            await quizService.createQuizWithContent(content.id, quizSettings);
          }
        } catch (quizError: any) {
          console.error("Error updating quiz:", quizError);
          alert("Nội dung đã được cập nhật nhưng có lỗi khi cập nhật quiz settings.");
        }
      }

      alert("Cập nhật nội dung thành công!");
      onSuccess();
    } catch (error: any) {
      console.error("Error updating content:", error);
      alert(error.response?.data?.error || "Lỗi khi cập nhật nội dung");
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes?: number): string => {
    if (!bytes) return "";
    const mb = bytes / (1024 * 1024);
    return mb < 1 ? `${(bytes / 1024).toFixed(1)} KB` : `${mb.toFixed(1)} MB`;
  };

  const currentFile =
    uploadedFile ||
    (formData.metadata?.file_path
      ? {
          file_id: formData.metadata.file_id || "",
          file_name: formData.metadata.file_name || "",
          file_path: formData.metadata.file_path,
          file_url: "",
          file_size: formData.metadata.file_size || 0,
          file_type: content.type,
        }
      : null);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b sticky top-0 bg-white z-10">
          <h2 className="text-xl font-bold">Chỉnh sửa nội dung</h2>
          <p className="text-sm text-gray-600 mt-1">
            {getContentTypeLabel(content.type)} - {content.title}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Type Info */}
          <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-700">
              <strong>Loại nội dung:</strong> {getContentTypeLabel(content.type)}
              <br />
              <strong>Ngày tạo:</strong>{" "}
              {new Date(content.metadata?.created_at || "").toLocaleDateString(
                "vi-VN"
              )}
            </p>
          </div>

          {/* Title */}
          <div>
            <label className="block text-sm font-medium mb-2">Tiêu đề *</label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => handleTitleChange(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              required
              disabled={loading}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium mb-2">Mô tả</label>
            <textarea
              value={formData.description}
              onChange={(e) => handleDescriptionChange(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              rows={3}
              disabled={loading}
            />
          </div>

          {/* QUIZ Settings */}
          {content.type === "QUIZ" && quizSettings && (
            <div className="border-t pt-4">
              {loadingQuiz ? (
                <div className="text-center py-4">
                  <div className="inline-block w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                  <p className="text-sm text-gray-600 mt-2">Đang tải cài đặt quiz...</p>
                </div>
              ) : (
                <QuizSettingsForm
                  settings={quizSettings}
                  onChange={setQuizSettings}
                  disabled={loading}
                />
              )}
            </div>
          )}

          {/* Text Content for TEXT type */}
          {content.type === "TEXT" && (
            <div>
              <label className="block text-sm font-medium mb-2">
                Nội dung văn bản *
              </label>
              <textarea
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
                className="w-full px-4 py-2 border rounded-lg font-mono text-sm focus:ring-2 focus:ring-blue-500"
                rows={8}
                placeholder="Nhập nội dung bài học..."
                disabled={loading}
              />
              <p className="text-xs text-gray-500 mt-1">
                Hỗ trợ Markdown. Bạn có thể sử dụng **bold**, *italic*, `code`, etc.
              </p>
            </div>
          )}

          {/* File Upload Section for File-based Content */}
          {(content.type === "VIDEO" ||
            content.type === "DOCUMENT" ||
            content.type === "IMAGE") && (
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="block text-sm font-medium">File</label>
                {currentFile && (
                  <button
                    type="button"
                    onClick={() => setShowFileUpload(!showFileUpload)}
                    className="text-xs text-blue-600 hover:text-blue-700"
                  >
                    {showFileUpload ? "Hủy" : "Đổi file"}
                  </button>
                )}
              </div>

              {currentFile && !showFileUpload && (
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg mb-4">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-green-700 mb-1">
                        ✓ File hiện tại
                      </p>
                      <p className="text-sm text-green-600">
                        📁 {currentFile.file_name}
                      </p>
                      <p className="text-xs text-green-600">
                        📊 {formatFileSize(currentFile.file_size)}
                      </p>
                      <p className="text-xs text-gray-500 mt-1 font-mono break-all">
                        {currentFile.file_path}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setRemoveFileConfirm(true)}
                      className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                    >
                      Xóa
                    </button>
                  </div>

                  {removeFileConfirm && (
                    <div className="mt-3 p-3 bg-red-100 border border-red-300 rounded text-sm">
                      <p className="text-red-700 mb-2">
                        Bạn có chắc muốn xóa file này?
                      </p>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={removeCurrentFile}
                          className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700"
                        >
                          Xác nhận xóa
                        </button>
                        <button
                          type="button"
                          onClick={() => setRemoveFileConfirm(false)}
                          className="px-3 py-1 bg-gray-300 text-gray-700 rounded text-sm hover:bg-gray-400"
                        >
                          Hủy
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {showFileUpload && (
                <div className="mb-4">
                  <FileUpload
                    fileType={getFileUploadType(content.type)}
                    onFileUploaded={handleFileUploaded}
                  />
                </div>
              )}

              {!currentFile && (
                <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-sm text-yellow-700 mb-3">
                    ⚠️ Chưa có file được tải lên
                  </p>
                  <FileUpload
                    fileType={getFileUploadType(content.type)}
                    onFileUploaded={handleFileUploaded}
                  />
                </div>
              )}
            </div>
          )}

          {/* Order Index */}
          <div>
            <label className="block text-sm font-medium mb-2">Thứ tự</label>
            <input
              type="number"
              value={formData.order_index}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  order_index: parseInt(e.target.value) || 0,
                })
              }
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              min="0"
              disabled={loading}
            />
          </div>

          {/* Mandatory Checkbox */}
          <div className="flex items-center">
            <input
              type="checkbox"
              id="is-mandatory"
              checked={formData.is_mandatory}
              onChange={(e) =>
                setFormData({ ...formData, is_mandatory: e.target.checked })
              }
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              disabled={loading}
            />
            <label htmlFor="is-mandatory" className="ml-2 text-sm font-medium">
              Nội dung bắt buộc
            </label>
          </div>

          {/* Info */}
          {content.type !== "QUIZ" && (
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-700">
                <strong>💡 Lưu ý:</strong> Khi bạn cập nhật file, học viên sẽ nhận
                được file mới khi họ truy cập lại nội dung. Tiêu đề và mô tả cũng sẽ
                được cập nhật ngay lập tức.
              </p>
            </div>
          )}
        </form>

        {/* Actions */}
        <div className="flex gap-3 p-6 border-t sticky bottom-0 bg-white">
          <Button
            type="submit"
            onClick={handleSubmit}
            disabled={loading || loadingQuiz}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {loading ? "Đang cập nhật..." : "✓ Cập nhật"}
          </Button>
          {content.type === "QUIZ" && quizId && (
            <Button
              type="button"
              onClick={() => router.push(`/lms/teacher/quiz/${quizId}/manage`)}
              disabled={loading}
              className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              📝 Quản lý Quiz
            </Button>
          )}
          <Button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 disabled:opacity-50"
          >
            Hủy
          </Button>
        </div>
      </div>
    </div>
  );
}