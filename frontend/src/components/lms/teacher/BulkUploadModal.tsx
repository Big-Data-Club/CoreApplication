"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import lmsService from "@/services/lmsService";
import { FileToUpload } from "@/types";

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

  const uploadSingleFile = (fileItem: FileToUpload): Promise<any> => {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append("file", fileItem.file);
      formData.append("type", fileItem.type);

      const xhr = new XMLHttpRequest();

      xhr.addEventListener("load", () => {
        if (xhr.status === 200) {
          try {
            const response = JSON.parse(xhr.responseText);
            if (response.data) {
              resolve(response.data);
            } else {
              reject(new Error("Invalid response format"));
            }
          } catch (e) {
            reject(new Error("Failed to parse response"));
          }
        } else {
          try {
            const errorResponse = JSON.parse(xhr.responseText);
            reject(new Error(errorResponse.error || `HTTP ${xhr.status}`));
          } catch {
            reject(new Error(`Upload failed (${xhr.status})`));
          }
        }
      });

      xhr.addEventListener("error", () => {
        reject(new Error("Connection error"));
      });

      xhr.addEventListener("abort", () => {
        reject(new Error("Upload cancelled"));
      });

      const apiUrl =
        process.env.NEXT_PUBLIC_LMS_API_URL || "http://localhost:8081/api/v1";
      const cookies = document.cookie.split(";");
      const authCookie = cookies.find((c) => c.trim().startsWith("authToken="));
      const token = authCookie ? authCookie.split("=")[1] : null;

      if (!token) {
        reject(new Error("No authentication token found"));
        return;
      }

      xhr.open("POST", `${apiUrl}/files/upload`);
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.send(formData);
    });
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
        <div className="p-6 border-b sticky top-0 bg-white z-10">
          <h2 className="text-xl font-bold">Tải lên nhiều file</h2>
          <p className="text-sm text-gray-600 mt-1">
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
              className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                dragOver
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-300 bg-gray-50"
              }`}
            >
              <div className="text-4xl mb-3">📁</div>
              <p className="text-gray-700 font-medium mb-2">
                Kéo thả file vào đây hoặc nhấp để chọn
              </p>
              <p className="text-sm text-gray-500 mb-4">
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
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
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
                  className="px-3 py-1 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
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

              {filesToUpload.map((fileItem, idx) => (
                <div
                  key={fileItem.id}
                  className="p-4 border rounded-lg space-y-3"
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
                          <p className="text-xs text-gray-500">
                            {formatFileSize(fileItem.file.size)}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Status Icon */}
                    {fileItem.uploadStatus === "pending" && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                        Chờ
                      </span>
                    )}
                    {fileItem.uploadStatus === "uploading" && (
                      <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded">
                        ⏳ Đang tải
                      </span>
                    )}
                    {fileItem.uploadStatus === "success" && (
                      <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded">
                        ✓ Thành công
                      </span>
                    )}
                    {fileItem.uploadStatus === "error" && (
                      <span className="px-2 py-1 bg-red-100 text-red-700 text-xs rounded">
                        ✕ Lỗi
                      </span>
                    )}
                  </div>

                  {/* Title Input */}
                  <div>
                    <label className="text-sm font-medium mb-1 block">
                      Tiêu đề *
                    </label>
                    <input
                      type="text"
                      value={fileItem.title}
                      onChange={(e) =>
                        updateFile(fileItem.id, { title: e.target.value })
                      }
                      className="w-full px-3 py-2 border rounded text-sm focus:ring-2 focus:ring-blue-500"
                      placeholder="Nhập tiêu đề nội dung..."
                      disabled={isUploading}
                    />
                  </div>

                  {/* Description Input */}
                  <div>
                    <label className="text-sm font-medium mb-1 block">
                      Mô tả
                    </label>
                    <textarea
                      value={fileItem.description}
                      onChange={(e) =>
                        updateFile(fileItem.id, { description: e.target.value })
                      }
                      className="w-full px-3 py-2 border rounded text-sm focus:ring-2 focus:ring-blue-500"
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
                      className="w-4 h-4 text-blue-600 rounded"
                      disabled={isUploading}
                    />
                    <label
                      htmlFor={`mandatory-${fileItem.id}`}
                      className="ml-2 text-sm font-medium"
                    >
                      Nội dung bắt buộc
                    </label>
                  </div>

                  {/* Error Message */}
                  {fileItem.uploadError && (
                    <div className="p-2 bg-red-50 border border-red-200 rounded text-red-700 text-xs">
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
            <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
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
        <div className="flex gap-3 p-6 border-t sticky bottom-0 bg-white">
          <Button
            type="button"
            onClick={uploadFiles}
            disabled={isUploading || filesToUpload.length === 0}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isUploading ? "Đang tải lên..." : "✓ Tải lên tất cả"}
          </Button>
          <Button
            type="button"
            onClick={onClose}
            disabled={isUploading}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 disabled:opacity-50"
          >
            Đóng
          </Button>
        </div>
      </div>
    </div>
  );
}
