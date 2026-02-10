/* eslint-disable @next/next/no-img-element */
"use client";

import { useState, useRef } from "react";
import { Upload, X, Image as ImageIcon, Loader2, ZoomIn, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import quizService from "@/services/quizService";

// Interface khớp với Backend (quiz_dto.go)
export interface QuestionImage {
  id: string;              // Backend trả về UUID string
  url: string;             // Backend trả về key 'url'
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

interface QuestionImageUploaderProps {
  questionId: number | null;
  images: QuestionImage[];
  onImagesUpdate: () => void;
  disabled?: boolean;
}

export default function QuestionImageUploader({
  questionId,
  images,
  onImagesUpdate,
  disabled = false,
}: QuestionImageUploaderProps) {
  const [uploading, setUploading] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0 || !questionId) return;

    const validFiles = Array.from(files).filter((file) => {
      const isImage = file.type.startsWith("image/");
      const isValidSize = file.size <= 5 * 1024 * 1024; // 5MB
      
      if (!isImage) {
        alert(`${file.name} không phải là file ảnh hợp lệ`);
        return false;
      }
      if (!isValidSize) {
        alert(`${file.name} vượt quá 5MB`);
        return false;
      }
      return true;
    });

    if (validFiles.length === 0) return;

    setUploading(true);
    setUploadProgress(0);
    
    try {
      for (let i = 0; i < validFiles.length; i++) {
        await quizService.uploadQuestionImage(questionId, validFiles[i]);
        setUploadProgress(Math.round(((i + 1) / validFiles.length) * 100));
      }
      
      onImagesUpdate();
      // alert(`✅ Đã upload thành công ${validFiles.length} ảnh`); // Có thể bỏ alert cho mượt
    } catch (error: any) {
      console.error("Error uploading images:", error);
      alert(error.response?.data?.message || "Không thể upload ảnh");
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDelete = async (imageId: string) => { // ID là string
    if (!questionId || !confirm("Bạn có chắc muốn xóa ảnh này?")) return;

    try {
      // Backend api nhận imageId là string nhưng hàm service của bạn có thể đang để number
      // Hãy đảm bảo service nhận string hoặc ép kiểu any tạm thời nếu cần
      await quizService.deleteQuestionImage(questionId, imageId as any); 
      onImagesUpdate();
    } catch (error: any) {
      console.error("Error deleting image:", error);
      alert(error.response?.data?.message || "Không thể xóa ảnh");
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  if (!questionId) {
    return (
      <div className="bg-gradient-to-r from-amber-50 to-orange-50 border-2 border-amber-200 rounded-xl p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-semibold text-amber-900 mb-1">Lưu câu hỏi trước</p>
            <p className="text-sm text-amber-700">
              Bạn cần lưu câu hỏi trước khi có thể thêm hình ảnh minh họa
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Upload Area */}
      <div className="relative">
        <div
          className={`relative border-2 border-dashed rounded-2xl p-8 transition-all duration-300 ${
            dragActive
              ? "border-blue-500 bg-blue-50 scale-[1.02]"
              : "border-gray-300 hover:border-blue-400 hover:bg-gray-50"
          } ${disabled || uploading ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !disabled && !uploading && fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*"
            onChange={(e) => handleFileSelect(e.target.files)}
            className="hidden"
            disabled={disabled || uploading}
          />

          <div className="flex flex-col items-center justify-center gap-4">
            {uploading ? (
              <>
                <div className="relative">
                  <Loader2 className="w-16 h-16 text-blue-500 animate-spin" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-xs font-bold text-blue-600">
                      {uploadProgress}%
                    </span>
                  </div>
                </div>
                <p className="text-sm text-gray-600 font-medium">Đang upload hình ảnh...</p>
                <div className="w-64 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all duration-300 rounded-full"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </>
            ) : (
              <>
                <div className="relative">
                  <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-lg transform transition-transform hover:scale-110">
                    <Upload className="w-10 h-10 text-white" />
                  </div>
                  <div className="absolute -bottom-1 -right-1 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center shadow-md">
                    <span className="text-white text-lg">+</span>
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-base font-semibold text-gray-800 mb-2">
                    Kéo thả ảnh vào đây hoặc click để chọn
                  </p>
                  <p className="text-sm text-gray-500">
                    Hỗ trợ: PNG, JPG, GIF, WEBP • Tối đa 5MB/ảnh
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Images Grid */}
      {images.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-base font-bold text-gray-800 flex items-center gap-2">
              <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
                <ImageIcon className="w-4 h-4 text-blue-600" />
              </div>
              Hình ảnh đính kèm ({images.length})
            </h4>
            <span className="text-xs text-gray-500 bg-gray-100 px-3 py-1 rounded-full">
              Tổng: {formatFileSize(images.reduce((sum, img) => sum + img.file_size, 0))}
            </span>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {images
              // Backend không có order_index, sort theo thời gian tạo
              .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
              .map((image, index) => (
                <div
                  key={image.id}
                  className="group relative bg-white border-2 border-gray-200 rounded-xl overflow-hidden hover:shadow-xl hover:border-blue-400 transition-all duration-300 transform hover:-translate-y-1"
                >
                  {/* Image Number Badge */}
                  <div className="absolute top-2 left-2 z-10 w-7 h-7 bg-black bg-opacity-70 rounded-full flex items-center justify-center">
                    <span className="text-xs font-bold text-white">{index + 1}</span>
                  </div>

                  {/* Image */}
                  <div className="aspect-square relative bg-gradient-to-br from-gray-100 to-gray-200">
                    <img
                      src={image.url} // Sửa thành .url
                      alt={image.caption || image.file_name}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                    
                    {/* Overlay Actions */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-end justify-center gap-2 pb-3">
                      <Button
                        type="button"
                        size="sm"
                        className="bg-white hover:bg-gray-100 text-gray-800 shadow-lg"
                        onClick={() => setPreviewImage(image.url)} // Sửa thành .url
                      >
                        <ZoomIn className="w-4 h-4 mr-1" />
                        Xem
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        className="shadow-lg"
                        onClick={() => handleDelete(image.id)}
                        disabled={disabled}
                      >
                        <X className="w-4 h-4 mr-1" />
                        Xóa
                      </Button>
                    </div>
                  </div>

                  {/* Info */}
                  <div className="p-2.5 border-t bg-gradient-to-r from-gray-50 to-white">
                    <p className="text-xs font-semibold text-gray-700 truncate mb-1">
                      {image.file_name}
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500">
                        {formatFileSize(image.file_size)}
                      </span>
                      <span className="text-xs text-green-600 font-medium">
                        ✓ Uploaded
                      </span>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Image Preview Modal */}
      {previewImage && (
        <div
          className="fixed inset-0 bg-black bg-opacity-95 z-50 flex items-center justify-center p-4 animate-in fade-in duration-200"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-7xl max-h-full">
            <Button
              type="button"
              size="sm"
              className="absolute -top-14 right-0 bg-white hover:bg-gray-100 text-gray-800 shadow-lg"
              onClick={(e) => {
                e.stopPropagation();
                setPreviewImage(null);
              }}
            >
              <X className="w-4 h-4 mr-2" />
              Đóng (ESC)
            </Button>
            <img
              src={previewImage}
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