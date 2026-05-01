"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import lmsService from "@/services/lmsService";
import { FileToUpload } from "@/types";
import { getAccessToken } from "@/services/authToken";


interface BulkUploadModalProps {
  sectionId: number;
  onClose: () => void;
  onSuccess: () => void;
}

export default function BulkUploadModal({
  sectionId,
  onClose,
  onSuccess,
}: BulkUploadModalProps) {
  const [filesToUpload, setFilesToUpload] = useState<FileToUpload[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const dropZoneRef = useRef<HTMLDivElement>(null);

  // Detect file type from extension
  const detectFileType = (filename: string): "video" | "document" | "image" => {
    const ext = filename.toLowerCase().split(".").pop() || "";
    const videoExts = ["mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "m4v"];
    const docExts = ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "csv"];
    const imageExts = ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"];

    if (videoExts.includes(ext)) return "video";
    if (docExts.includes(ext)) return "document";
    if (imageExts.includes(ext)) return "image";
    return "document";
  };

  const handleFileSelect = (files: FileList | null) => {
    if (!files) return;

    const newFiles: FileToUpload[] = Array.from(files).map((file) => ({
      id: Math.random().toString(36).substr(2, 9),
      file,
      type: detectFileType(file.name),
      title: file.name.replace(/\.[^/.]+$/, ""),
      description: "",
      isMandatory: false,
      uploadedFile: null,
      uploadError: "",
      uploadStatus: "pending" as const,
    }));

    setFilesToUpload((prev) => [...prev, ...newFiles]);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);

    if (e.dataTransfer.files) {
      handleFileSelect(e.dataTransfer.files);
    }
  };

  const updateFile = (id: string, updates: Partial<FileToUpload>) => {
    setFilesToUpload((prev) =>
      prev.map((f) => (f.id === id ? { ...f, ...updates } : f))
    );
  };

  const removeFile = (id: string) => {
    setFilesToUpload((prev) => prev.filter((f) => f.id !== id));
  };

  const uploadFiles = async () => {
    if (filesToUpload.length === 0) {
      alert("Vui lòng chọn ít nhất một file");
      return;
    }

    // Validate all files have titles
    const hasEmptyTitles = filesToUpload.some((f) => !f.title.trim());
    if (hasEmptyTitles) {
      alert("Vui lòng nhập tiêu đề cho tất cả các file");
      return;
    }

    setIsUploading(true);

    try {
      // Upload all files sequentially
      for (const fileItem of filesToUpload) {
        if (fileItem.uploadStatus === "pending") {
          updateFile(fileItem.id, { uploadStatus: "uploading" });

          try {
            // Upload file
            const uploadedFile = await uploadSingleFile(fileItem);

            // Create content in LMS
            await lmsService.createContent(sectionId, {
              type:
                fileItem.type === "video"
                  ? "VIDEO"
                  : fileItem.type === "image"
                    ? "IMAGE"
                    : "DOCUMENT",
              title: fileItem.title.trim(),
              description: fileItem.description.trim(),
              order_index: filesToUpload.indexOf(fileItem),
              is_mandatory: fileItem.isMandatory,
              metadata: {
                file_path: uploadedFile.file_path,
                file_name: uploadedFile.file_name,
                file_size: uploadedFile.file_size,
                file_id: uploadedFile.file_id,
              },
            });

            updateFile(fileItem.id, {
              uploadStatus: "success",
              uploadedFile,
            });
          } catch (error: any) {
            console.error(`Error uploading ${fileItem.file.name}:`, error);
            updateFile(fileItem.id, {
              uploadStatus: "error",
              uploadError:
                error.response?.data?.error ||
                error.message ||
                "Lỗi không xác định",
            });
          }
        }
      }

      setIsUploading(false);
      const successCount = filesToUpload.filter(
        (f) => f.uploadStatus === "success"
      ).length;

      if (successCount > 0) {
        alert(`Đã tải lên thành công ${successCount}/${filesToUpload.length} file`);
        onSuccess();
      }
    } catch (error) {
      console.error("Upload error:", error);
      alert("Lỗi khi tải lên các file");
      setIsUploading(false);
    }
  };

  const uploadSingleFile = async (fileItem: FileToUpload): Promise<any> => {
    const formData = new FormData();
    formData.append("file", fileItem.file);
    formData.append("type", fileItem.type);

    const headers: Record<string, string> = {};
    const token = await getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch("/lmsapiv1/files/upload", {
      method: "POST",
      body: formData,
      credentials: "include",
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `HTTP ${response.status}`);
    }

    const result = await response.json();
    if (!result.data) {
      throw new Error("Invalid response format");
    }

    return result.data;
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
  };

  const getTypeIcon = (type: string) => {
    const icons: Record<string, string> = {
      video: "🎥",
      document: "📄",
      image: "🖼️",
    };
    return icons[type] || "📎";
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-slate-200 dark:border-slate-800 sticky top-0 bg-white dark:bg-slate-900 z-10">
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-50">Tải lên nhiều file</h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Chọn hoặc kéo thả nhiều file để tải lên cùng lúc
          </p>
        </div>

        <div className="p-6 space-y-6">
          {/* Drop Zone */}
          {filesToUpload.length === 0 && (
            <div
              ref={dropZoneRef}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-2xl p-8 text-center transition-colors ${
                dragOver
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                  : "border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50"
              }`}
            >
              <div className="text-4xl mb-3">📁</div>
              <p className="text-slate-700 dark:text-slate-300 font-medium mb-2">
                Kéo thả file vào đây hoặc nhấp để chọn
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-500 mb-4">
                Hỗ trợ: Video, Hình ảnh, Tài liệu (Max 100MB mỗi file)
              </p>
              <input
                type="file"
                multiple
                onChange={(e) => handleFileSelect(e.target.files)}
                className="hidden"
                id="bulk-file-input"
              />
              <label htmlFor="bulk-file-input">
                <Button
                  type="button"
                  onClick={() =>
                    document.getElementById("bulk-file-input")?.click()
                  }
                  className="px-6 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-medium transition-colors"
                >
                  Chọn file
                </Button>
              </label>
            </div>
          )}

          {/* Files List */}
          {filesToUpload.length > 0 && (
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <h3 className="font-semibold">
                  Danh sách file ({filesToUpload.length})
                </h3>
                <Button
                  type="button"
                  onClick={() =>
                    document.getElementById("bulk-file-input")?.click()
                  }
                  className="px-3 py-1 text-sm bg-slate-600 dark:bg-slate-700 text-white rounded-lg hover:bg-slate-700 dark:hover:bg-slate-600 font-medium transition-colors"
                >
                  Thêm file
                </Button>
              </div>
              <input
                type="file"
                multiple
                onChange={(e) => handleFileSelect(e.target.files)}
                className="hidden"
                id="bulk-file-input"
              />

              {filesToUpload.map((fileItem) => (
                <div
                  key={fileItem.id}
                  className="p-4 border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 space-y-3 hover:border-slate-300 dark:hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-2xl">
                          {getTypeIcon(fileItem.type)}
                        </span>
                        <div>
                          <p className="font-medium text-sm">
                            {fileItem.file.name}
                          </p>
                          <p className="text-xs text-slate-500 dark:text-slate-400">
                            {formatFileSize(fileItem.file.size)}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Status Icon */}
                    {fileItem.uploadStatus === "pending" && (
                      <span className="px-2 py-1 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs rounded-lg font-medium">
                        Chờ
                      </span>
                    )}
                    {fileItem.uploadStatus === "uploading" && (
                      <span className="px-2 py-1 bg-blue-50 dark:bg-blue-950/20 text-blue-700 dark:text-blue-400 text-xs rounded-lg font-medium">
                        ⏳ Đang tải
                      </span>
                    )}
                    {fileItem.uploadStatus === "success" && (
                      <span className="px-2 py-1 bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400 text-xs rounded-lg font-medium">
                        ✓ Thành công
                      </span>
                    )}
                    {fileItem.uploadStatus === "error" && (
                      <span className="px-2 py-1 bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400 text-xs rounded-lg font-medium">
                        ✕ Lỗi
                      </span>
                    )}
                  </div>

                  {/* Title Input */}
                  <div>
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                      Tiêu đề *
                    </label>
                    <input
                      type="text"
                      value={fileItem.title}
                      onChange={(e) =>
                        updateFile(fileItem.id, { title: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                      placeholder="Nhập tiêu đề nội dung..."
                      disabled={isUploading}
                    />
                  </div>

                  {/* Description Input */}
                  <div>
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                      Mô tả
                    </label>
                    <textarea
                      value={fileItem.description}
                      onChange={(e) =>
                        updateFile(fileItem.id, { description: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                      placeholder="Nhập mô tả..."
                      rows={2}
                      disabled={isUploading}
                    />
                  </div>

                  {/* Mandatory Checkbox */}
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id={`mandatory-${fileItem.id}`}
                      checked={fileItem.isMandatory}
                      onChange={(e) =>
                        updateFile(fileItem.id, { isMandatory: e.target.checked })
                      }
                      className="w-4 h-4 text-blue-600 border-slate-300 dark:border-slate-600 rounded"
                      disabled={isUploading}
                    />
                    <label
                      htmlFor={`mandatory-${fileItem.id}`}
                      className="ml-2 text-sm font-medium text-slate-700 dark:text-slate-300"
                    >
                      Nội dung bắt buộc
                    </label>
                  </div>

                  {/* Error Message */}
                  {fileItem.uploadError && (
                    <div className="p-2 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400 text-xs">
                      {fileItem.uploadError}
                    </div>
                  )}

                  {/* Remove Button */}
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      onClick={() => removeFile(fileItem.id)}
                      className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                      disabled={isUploading}
                    >
                      Xóa
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Summary */}
          {filesToUpload.length > 0 && (
            <div className="p-3 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg text-sm text-blue-700 dark:text-blue-400">
              💡 Đã chọn <strong>{filesToUpload.length}</strong> file.{" "}
              {filesToUpload.filter((f) => f.uploadStatus === "success").length >
                0 && (
                <>
                  {filesToUpload.filter((f) => f.uploadStatus === "success")
                    .length}{" "}
                  đã tải lên thành công.
                </>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3 p-6 border-t border-slate-200 dark:border-slate-800 sticky bottom-0 bg-white dark:bg-slate-900">
          <Button
            type="button"
            onClick={uploadFiles}
            disabled={isUploading || filesToUpload.length === 0}
            className="flex-1 px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-all"
          >
            {isUploading ? "Đang tải lên..." : "✓ Tải lên tất cả"}
          </Button>
          <Button
            type="button"
            onClick={onClose}
            disabled={isUploading}
            className="px-4 py-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50 font-medium transition-colors"
          >
            Đóng
          </Button>
        </div>
      </div>
    </div>
  );
}
