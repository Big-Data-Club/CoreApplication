"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import FileUpload from "@/components/lms/teacher/FileUpload";
import lmsService from "@/services/lmsService";
import { Content, ContentType, FileInfo } from "@/types";

interface ContentModalProps {
  sectionId: number;
  onClose: () => void;
  onSuccess: () => void;
  existingContents: Content[];
}

export default function ContentModal({ 
  sectionId, 
  onClose, 
  onSuccess, 
  existingContents 
}: ContentModalProps) {
  const [formData, setFormData] = useState({
    type: "TEXT" as ContentType,
    title: "",
    description: "",
    order_index: existingContents.length,
    is_mandatory: false,
    metadata: {} as Record<string, any>,
  });
  const [loading, setLoading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<FileInfo | null>(null);
  const [textContent, setTextContent] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [imageUrl, setImageUrl] = useState("");

  const contentTypes = [
    { value: "TEXT", label: "Văn bản", needsUpload: false },
    { value: "VIDEO", label: "Video", needsUpload: true, fileType: "video" as const },
    { value: "DOCUMENT", label: "Tài liệu", needsUpload: true, fileType: "document" as const },
    { value: "IMAGE", label: "Hình ảnh", needsUpload: true, fileType: "image" as const },
    { value: "QUIZ", label: "Quiz", needsUpload: false },
    { value: "FORUM", label: "Diễn đàn", needsUpload: false },
    { value: "ANNOUNCEMENT", label: "Thông báo", needsUpload: false },
  ];

  const selectedContentType = contentTypes.find(ct => ct.value === formData.type);

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

    if (!formData.title) {
      setFormData(prev => ({
        ...prev,
        title: fileInfo.file_name,
        metadata: {
          ...prev.metadata,
          file_path: fileInfo.file_path,
          file_name: fileInfo.file_name,
          file_size: fileInfo.file_size,
          file_id: fileInfo.file_id,
        },
      }));
    }
  };

  const handleTypeChange = (newType: string) => {
    setUploadedFile(null);
    setTextContent("");
    setVideoUrl("");
    setImageUrl("");
    
    setFormData({
      ...formData,
      type: newType as ContentType,
      metadata: {},
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const metadata = { ...formData.metadata };

    if (formData.type === "TEXT") {
      metadata.content = textContent;
    } else if (formData.type === "VIDEO") {
      if (uploadedFile) {
        metadata.video_type = "uploaded";
      } else if (videoUrl) {
        metadata.video_url = videoUrl;
        metadata.video_type = "external";
      } else {
        alert("Vui lòng upload video hoặc nhập URL video");
        return;
      }
    } else if (formData.type === "IMAGE") {
      if (uploadedFile) {
        metadata.image_type = "uploaded";
      } else if (imageUrl) {
        metadata.image_url = imageUrl;
        metadata.image_type = "external";
      } else {
        alert("Vui lòng upload ảnh hoặc nhập URL ảnh");
        return;
      }
    } else if (formData.type === "DOCUMENT") {
      if (!uploadedFile) {
        alert("Vui lòng upload tài liệu");
        return;
      }
      metadata.document_type = "uploaded";
    }

    try {
      setLoading(true);
      await lmsService.createContent(sectionId, {
        ...formData,
        metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
      });
      alert("Tạo nội dung thành công!");
      onSuccess();
    } catch (error: any) {
      console.error("Error creating content:", error);
      alert(error.response?.data?.error || "Lỗi khi tạo nội dung");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b sticky top-0 bg-white z-10">
          <h2 className="text-xl font-bold">Thêm nội dung mới</h2>
        </div>
        <form onSubmit={handleSubmit} className="p-6">
          <div className="space-y-4">
            {/* Content Type */}
            <div>
              <label className="block text-sm font-medium mb-2">Loại nội dung *</label>
              <select
                value={formData.type}
                onChange={(e) => handleTypeChange(e.target.value)}
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                required
              >
                {contentTypes.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>

            {/* File Upload for VIDEO, DOCUMENT, IMAGE */}
            {selectedContentType?.needsUpload && (
              <div>
                <label className="block text-sm font-medium mb-2">
                  Upload {selectedContentType.label} *
                </label>
                <FileUpload
                  fileType={selectedContentType.fileType || "document"}
                  onFileUploaded={handleFileUploaded}
                />
                {uploadedFile && (
                  <div className="mt-3 p-4 bg-green-50 border border-green-200 rounded-lg">
                    <p className="text-sm font-medium text-green-700 mb-1">
                      ✅ Đã upload thành công
                    </p>
                    <p className="text-sm text-green-600">
                      📁 {uploadedFile.file_name}
                    </p>
                    <p className="text-xs text-green-600">
                      📊 {(uploadedFile.file_size / 1024 / 1024).toFixed(2)} MB
                    </p>
                    <p className="text-xs text-gray-500 mt-1 font-mono">
                      Path: {uploadedFile.file_path}
                    </p>
                  </div>
                )}

                {/* Alternative: External URL for VIDEO and IMAGE */}
                {(formData.type === "VIDEO" || formData.type === "IMAGE") && (
                  <div className="mt-3">
                    <label className="block text-sm font-medium mb-2">
                      Hoặc nhập URL {formData.type === "VIDEO" ? "video" : "ảnh"} từ internet
                    </label>
                    <input
                      type="url"
                      value={formData.type === "VIDEO" ? videoUrl : imageUrl}
                      onChange={(e) => 
                        formData.type === "VIDEO" 
                          ? setVideoUrl(e.target.value)
                          : setImageUrl(e.target.value)
                      }
                      placeholder={formData.type === "VIDEO" 
                        ? "https://youtube.com/watch?v=... hoặc https://example.com/video.mp4"
                        : "https://example.com/image.jpg"
                      }
                      className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                      disabled={!!uploadedFile}
                    />
                    {uploadedFile && (
                      <p className="text-xs text-gray-500 mt-1">
                        Đã có file upload. Xóa file để sử dụng URL
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Text Content for TEXT type */}
            {formData.type === "TEXT" && (
              <div>
                <label className="block text-sm font-medium mb-2">Nội dung văn bản *</label>
                <textarea
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  className="w-full px-4 py-2 border rounded-lg font-mono text-sm focus:ring-2 focus:ring-blue-500"
                  rows={10}
                  placeholder="Nhập nội dung bài học..."
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  Hỗ trợ Markdown. Bạn có thể sử dụng **bold**, *italic*, `code`, etc.
                </p>
              </div>
            )}

            {/* Title */}
            <div>
              <label className="block text-sm font-medium mb-2">Tiêu đề *</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Nhập tiêu đề nội dung..."
                required
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium mb-2">Mô tả</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                rows={3}
                placeholder="Mô tả ngắn về nội dung này..."
              />
            </div>

            {/* Order Index and Mandatory */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Thứ tự</label>
                <input
                  type="number"
                  value={formData.order_index}
                  onChange={(e) => setFormData({ ...formData, order_index: parseInt(e.target.value) || 0 })}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  min="0"
                />
              </div>
              <div className="flex items-center">
                <label className="flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.is_mandatory}
                    onChange={(e) => setFormData({ ...formData, is_mandatory: e.target.checked })}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span className="ml-2 text-sm font-medium">Nội dung bắt buộc</span>
                </label>
              </div>
            </div>

            {/* Info box */}
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-700">
                <strong>💡 Lưu ý:</strong> {" "}
                {formData.type === "TEXT" && "Nội dung văn bản sẽ được hiển thị trực tiếp trên trang."}
                {formData.type === "VIDEO" && "Video có thể upload hoặc nhúng từ YouTube, Vimeo."}
                {formData.type === "DOCUMENT" && "Tài liệu (PDF, Word, Excel) sẽ có thể xem và tải xuống."}
                {formData.type === "IMAGE" && "Hình ảnh sẽ được hiển thị trong bài học."}
                {formData.type === "QUIZ" && "Quiz cần được cấu hình thêm sau khi tạo."}
                {formData.type === "FORUM" && "Diễn đàn cho phép học viên thảo luận."}
                {formData.type === "ANNOUNCEMENT" && "Thông báo sẽ được gửi đến tất cả học viên."}
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 mt-6 pt-4 border-t">
            <Button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {loading ? "Đang tạo..." : "✓ Tạo nội dung"}
            </Button>
            <Button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 disabled:opacity-50"
            >
              Hủy
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}