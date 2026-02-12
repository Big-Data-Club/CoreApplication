/* eslint-disable @next/next/no-img-element */
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import quizService from "@/services/quizService";

interface ContentViewerProps {
  content: {
    id: number;
    type: string;
    title: string;
    description: string;
    metadata?: Record<string, any>;
    file_path?: string;
    file_type?: string;
  };
  userRole?: string; // 'TEACHER', 'STUDENT', 'ADMIN'
}

export default function ContentViewer({ content, userRole = 'STUDENT' }: ContentViewerProps) {
  const router = useRouter();
  const [error, setError] = useState<string>("");
  const [imageLoaded, setImageLoaded] = useState(false);
  
  // Quiz-specific state
  const [quizData, setQuizData] = useState<any>(null);
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizError, setQuizError] = useState<string>("");

  // Get API base URL
  const API_URL = process.env.NEXT_PUBLIC_LMS_API_URL;

  // Auto-fetch quiz data when content type is QUIZ
  useEffect(() => {
    if (content.type === "QUIZ") {
      fetchQuizData();
    }
  }, [content.id, content.type]);

  const fetchQuizData = async () => {
    setQuizLoading(true);
    setQuizError("");
    try {
      const response = await quizService.getQuizByContentId(content.id);
      console.log("Quiz data loaded:", response);
      setQuizData(response?.data);
    } catch (err: any) {
      console.error("Error loading quiz:", err);
      if (err.response?.status === 404) {
        setQuizError("Quiz chưa được tạo cho nội dung này");
      } else {
        setQuizError("Không thể tải thông tin quiz");
      }
      setQuizData(null);
    } finally {
      setQuizLoading(false);
    }
  };

  // Build file URL from file_path
  const buildFileUrl = (filePath: string | undefined): string => {
    if (!filePath) return "";
    
    if (filePath.startsWith("http://") || filePath.startsWith("https://")) {
      return filePath;
    }
    
    return `${API_URL}/files/serve/${filePath}`;
  };

  const renderContent = () => {
    switch (content.type) {
      case "TEXT":
        return (
          <div className="prose max-w-none">
            {content.metadata?.content ? (
              <ReactMarkdown>{content.metadata.content}</ReactMarkdown>
            ) : (
              <p className="text-gray-500">Chưa có nội dung</p>
            )}
          </div>
        );

      case "VIDEO":
        return renderVideo();

      case "IMAGE":
        return renderImage();

      case "DOCUMENT":
        return renderDocument();

      case "QUIZ":
        return renderQuiz();

      case "FORUM":
        return (
          <div className="p-6 bg-green-50 border border-green-200 rounded-lg">
            <h3 className="text-lg font-semibold mb-2">💬 Diễn đàn: {content.title}</h3>
            <p className="text-gray-700">{content.description}</p>
            <button className="mt-4 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
              Vào diễn đàn
            </button>
          </div>
        );

      case "ANNOUNCEMENT":
        return (
          <div className="p-6 bg-yellow-50 border border-yellow-200 rounded-lg">
            <h3 className="text-lg font-semibold mb-2">📢 Thông báo: {content.title}</h3>
            <p className="text-gray-700">{content.description}</p>
            {content.metadata?.content && (
              <div className="mt-4 prose max-w-none">
                <ReactMarkdown>{content.metadata.content}</ReactMarkdown>
              </div>
            )}
          </div>
        );

      default:
        return (
          <div className="p-4 bg-gray-100 rounded-lg">
            <p className="text-gray-600">Loại nội dung không được hỗ trợ</p>
          </div>
        );
    }
  };

  const renderQuiz = () => {
    const isTeacher = userRole === 'TEACHER' || userRole === 'ADMIN';
    const isStudent = userRole === 'STUDENT';
    
    // Show loading state
    if (quizLoading) {
      return (
        <div className="bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-200 rounded-xl p-8">
          <div className="flex items-center justify-center gap-3">
            <div className="w-6 h-6 border-3 border-purple-600 border-t-transparent rounded-full animate-spin"></div>
            <span className="text-gray-700">Đang tải thông tin quiz...</span>
          </div>
        </div>
      );
    }
    
    return (
      <div className="space-y-4">
        {/* Quiz Info Card */}
        <div className="bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-200 rounded-xl p-6">
          <div className="flex items-start gap-4">
            <div className="w-16 h-16 bg-purple-600 rounded-xl flex items-center justify-center flex-shrink-0">
              <span className="text-3xl">📝</span>
            </div>
            <div className="flex-1">
              <h3 className="text-2xl font-bold text-gray-900 mb-2">{content.title}</h3>
              <p className="text-gray-700 mb-4">{content.description || "Kiểm tra kiến thức của bạn"}</p>
              
              {/* Quiz Stats - Show from fetched quiz data */}
              {quizData && (
                <div className="flex gap-4 text-sm mb-4 flex-wrap">
                  {quizData.total_points && (
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-600">Tổng điểm:</span>
                      <span className="px-2 py-1 bg-white rounded font-semibold text-purple-700">
                        {quizData.total_points}
                      </span>
                    </div>
                  )}
                  {quizData.time_limit_minutes && (
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-600">Thời gian:</span>
                      <span className="px-2 py-1 bg-white rounded font-semibold text-purple-700">
                        {quizData.time_limit_minutes} phút
                      </span>
                    </div>
                  )}
                  {quizData.max_attempts && (
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-600">Số lần làm:</span>
                      <span className="px-2 py-1 bg-white rounded font-semibold text-purple-700">
                        {quizData.max_attempts > 0 ? `${quizData.max_attempts} lần` : 'Không giới hạn'}
                      </span>
                    </div>
                  )}
                  {quizData.passing_score && (
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-600">Điểm đạt:</span>
                      <span className="px-2 py-1 bg-white rounded font-semibold text-purple-700">
                        {quizData.passing_score}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Quiz availability info */}
              {quizData && (
                <div className="text-sm text-gray-600">
                  {quizData.available_from && (
                    <div>
                      📅 <strong>Mở từ:</strong> {new Date(quizData.available_from).toLocaleString('vi-VN')}
                    </div>
                  )}
                  {quizData.available_until && (
                    <div>
                      📅 <strong>Đến:</strong> {new Date(quizData.available_until).toLocaleString('vi-VN')}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Error message */}
        {quizError && (
          <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-4">
            <p className="text-yellow-700">
              ⚠️ {quizError}
            </p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          {isTeacher ? (
            <>
              {/* Teacher Actions */}
              {quizData?.id ? (
                <>
                  <button
                    onClick={() => router.push(`/lms/teacher/quiz/${quizData.id}/manage`)}
                    className="flex-1 px-6 py-4 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-semibold text-lg transition-all transform hover:scale-[1.02]"
                  >
                    ⚙️ Quản lý Quiz
                  </button>
                  <button
                    onClick={() => router.push(`/lms/teacher/quiz/${quizData.id}/grading`)}
                    className="flex-1 px-6 py-4 bg-green-600 text-white rounded-xl hover:bg-green-700 font-semibold text-lg transition-all transform hover:scale-[1.02]"
                  >
                    ✓ Chấm bài
                  </button>
                </>
              ) : (
                <button
                  onClick={() => router.push(`/lms/teacher/content/${content.id}/quiz/create`)}
                  className="flex-1 px-6 py-4 bg-purple-600 text-white rounded-xl hover:bg-purple-700 font-semibold text-lg transition-all transform hover:scale-[1.02]"
                >
                  + Tạo Quiz
                </button>
              )}
            </>
          ) : (
            <>
              {/* Student Actions */}
              {quizData?.id ? (
                <>
                  <button
                    onClick={() => router.push(`/lms/student/quiz/${quizData.id}/take`)}
                    className="flex-1 px-8 py-5 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-xl hover:from-purple-700 hover:to-indigo-700 font-bold text-xl transition-all transform hover:scale-[1.02] shadow-lg"
                  >
                    🚀 Bắt đầu làm bài
                  </button>
                  
                  {/* History Button for Students */}
                  {isStudent && (
                    <button
                      onClick={() => router.push(`/lms/student/quiz/${quizData.id}/history`)}
                      className="px-6 py-5 bg-white border-2 border-purple-300 text-purple-700 rounded-xl hover:bg-purple-50 font-semibold text-lg transition-all transform hover:scale-[1.02] flex items-center gap-2"
                    >
                      <span className="text-xl">📜</span>
                      Lịch sử
                    </button>
                  )}
                </>
              ) : (
                <div className="flex-1 px-6 py-4 bg-yellow-50 border border-yellow-300 rounded-xl">
                  <p className="text-yellow-700 text-center">
                    ⚠️ Quiz chưa được cấu hình. Vui lòng liên hệ giảng viên.
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Additional Info */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-800">
            <strong>💡 Lưu ý:</strong> 
            {isTeacher ? (
              " Bạn có thể quản lý câu hỏi, xem kết quả và chấm điểm cho học sinh."
            ) : (
              " Đọc kỹ hướng dẫn trước khi làm bài. Bạn có thể xem lại lịch sử các lần làm bài trước đó."
            )}
          </p>
        </div>
      </div>
    );
  };

  const renderVideo = () => {
    const videoUrl = content.metadata?.video_url || content.metadata?.url;
    
    if (!videoUrl) {
      return (
        <div className="p-4 bg-gray-100 rounded-lg">
          <p className="text-gray-600">Video chưa được cấu hình</p>
        </div>
      );
    }

    // Check video type
    const youtubeId = extractYouTubeId(videoUrl);
    const vimeoId = extractVimeoId(videoUrl);
    
    if (youtubeId) {
      return (
        <div className="aspect-video w-full">
          <iframe
            className="w-full h-full rounded-lg shadow-lg"
            src={`https://www.youtube.com/embed/${youtubeId}`}
            title={content.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      );
    }
    
    if (vimeoId) {
      return (
        <div className="aspect-video w-full">
          <iframe
            className="w-full h-full rounded-lg shadow-lg"
            src={`https://player.vimeo.com/video/${vimeoId}`}
            title={content.title}
            allow="autoplay; fullscreen; picture-in-picture"
            allowFullScreen
          />
        </div>
      );
    }

    // Direct video file
    const isVideoFile = /\.(mp4|webm|ogg)$/i.test(videoUrl);
    if (isVideoFile) {
      return (
        <div className="w-full">
          <video
            className="w-full rounded-lg shadow-lg"
            controls
            preload="metadata"
          >
            <source src={videoUrl} type={`video/${getFileExtension(videoUrl)}`} />
            Trình duyệt của bạn không hỗ trợ phát video.
          </video>
        </div>
      );
    }

    return (
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <p className="text-yellow-700">
          Video URL không được hỗ trợ. 
          <a href={videoUrl} target="_blank" rel="noopener noreferrer" className="underline ml-1">
            Xem tại đây
          </a>
        </p>
      </div>
    );
  };

  const renderImage = () => {
    const imagePath = content.metadata?.file_path || content.file_path;
    const imageUrl = imagePath 
      ? buildFileUrl(imagePath)
      : content.metadata?.image_url;
    
    if (!imageUrl) {
      return (
        <div className="p-4 bg-gray-100 rounded-lg">
          <p className="text-gray-600">Hình ảnh chưa được tải lên</p>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div className="relative bg-gray-100 rounded-lg overflow-hidden">
          {!imageLoaded && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
          )}
          <img
            src={imageUrl}
            alt={content.title}
            className={`w-full h-auto rounded-lg shadow-lg transition-opacity duration-300 ${
              imageLoaded ? "opacity-100" : "opacity-0"
            }`}
            onLoad={() => setImageLoaded(true)}
            onError={() => {
              setError("Không thể tải hình ảnh");
              setImageLoaded(true);
            }}
          />
        </div>
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            ⚠️ {error}
            <p className="text-xs mt-1">URL: {imageUrl}</p>
          </div>
        )}
        <div className="flex gap-2">
          <a
            href={imageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            🔍 Xem kích thước đầy đủ
          </a>
          <a
            href={imageUrl.replace("/serve/", "/download/")}
            download
            className="inline-flex items-center px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
          >
            📥 Tải xuống
          </a>
        </div>
      </div>
    );
  };

  const renderDocument = () => {
    const filePath = content.metadata?.file_path || content.file_path;
    const docUrl = filePath 
      ? buildFileUrl(filePath)
      : content.metadata?.file_url;
    
    if (!docUrl) {
      return (
        <div className="p-4 bg-gray-100 rounded-lg">
          <p className="text-gray-600">Tài liệu chưa được tải lên</p>
        </div>
      );
    }

    const isPdf = docUrl.toLowerCase().includes(".pdf");
    const fileName = content.metadata?.file_name || content.title;
    const fileSize = content.metadata?.file_size 
      ? formatFileSize(content.metadata.file_size) 
      : "Không rõ";

    const downloadUrl = docUrl.replace("/serve/", "/download/");

    return (
      <div className="space-y-4">
        <div className="p-6 bg-gray-50 border border-gray-200 rounded-lg">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                <span className="text-2xl">
                  {isPdf ? "📄" : "📋"}
                </span>
              </div>
            </div>
            <div className="flex-1">
              <h4 className="font-semibold text-lg mb-1">{fileName}</h4>
              <p className="text-sm text-gray-600 mb-3">Kích thước: {fileSize}</p>
              <div className="flex gap-2 flex-wrap">
                <a
                  href={docUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  👁️ Xem tài liệu
                </a>
                <a
                  href={downloadUrl}
                  download
                  className="inline-flex items-center px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                >
                  📥 Tải xuống
                </a>
              </div>
            </div>
          </div>
        </div>

        {isPdf && (
          <div className="border border-gray-300 rounded-lg overflow-hidden bg-gray-100">
            <iframe
              src={`${docUrl}#view=FitH`}
              className="w-full h-[600px]"
              title={fileName}
              onError={() => setError("Không thể hiển thị PDF. Vui lòng tải xuống để xem.")}
            />
            {error && (
              <div className="p-3 bg-yellow-50 border-t border-yellow-200 text-yellow-700 text-sm">
                ⚠️ {error}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  // Helper functions
  const extractYouTubeId = (url: string): string => {
    const patterns = [
      /(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/,
      /youtube\.com\/embed\/([^&\n?#]+)/,
    ];
    
    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match) return match[1];
    }
    
    return "";
  };

  const extractVimeoId = (url: string): string => {
    const match = url.match(/vimeo\.com\/(\d+)/);
    return match ? match[1] : "";
  };

  const getFileExtension = (url: string): string => {
    const parts = url.split(".");
    const ext = parts[parts.length - 1].toLowerCase();
    return ext.split("?")[0];
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  };

  return (
    <>
      <div className="space-y-4">
        {/* Content Header */}
        <div className="border-b pb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">
              {content.type}
            </span>
            {content.metadata?.is_mandatory && (
              <span className="px-2 py-1 bg-red-100 text-red-700 text-xs font-medium rounded">
                Bắt buộc
              </span>
            )}
          </div>
          <h2 className="text-2xl font-bold mb-2">{content.title}</h2>
          {content.description && content.type !== 'QUIZ' && (
            <p className="text-gray-600">{content.description}</p>
          )}
        </div>

        {/* Content Body */}
        {renderContent()}
        
        {/* Debug info in development */}
        {process.env.NODE_ENV === "development" && (
          <details className="text-xs bg-gray-100 p-3 rounded">
            <summary className="cursor-pointer font-mono">Debug Info</summary>
            <pre className="mt-2 overflow-auto">
              {JSON.stringify(
                {
                  type: content.type,
                  file_path: content.file_path,
                  metadata: content.metadata,
                  quiz_data: quizData,
                  built_url: content.metadata?.file_path 
                    ? buildFileUrl(content.metadata.file_path)
                    : "N/A"
                },
                null,
                2
              )}
            </pre>
          </details>
        )}
      </div>
    </>
  );
}