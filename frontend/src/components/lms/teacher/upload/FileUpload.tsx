"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { FileInfo } from "@/types";
import { getAccessToken } from "@/services/authToken";

interface FileUploadProps {
  onFileUploaded: (fileInfo: FileInfo) => void;
  fileType: "video" | "document" | "image";
  accept?: string;
  maxSize?: number; // in MB
  disabled?: boolean;
}

export default function FileUpload({
  onFileUploaded,
  fileType,
  accept,
  maxSize = 100,
  disabled = false,
}: FileUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const getAcceptString = () => {
    if (accept) return accept;
    
    switch (fileType) {
      case "video":
        return ".mp4,.avi,.mov,.mkv,.webm,.flv,.wmv,.m4v";
      case "document":
        return ".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.csv";
      case "image":
        return ".jpg,.jpeg,.png,.gif,.bmp,.svg,.webp";
      default:
        return "*";
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file size
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > maxSize) {
      setError(`File quá lớn. Kích thước tối đa: ${maxSize}MB`);
      return;
    }

    setError("");
    setUploading(true);
    setProgress(0);

    try {
      // Create FormData
      const formData = new FormData();
      formData.append("file", file);
      formData.append("type", fileType);

      // Upload via proxy
      const headers: Record<string, string> = {};
      const token = await getAccessToken();
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(`/lmsapiv1/files/upload`, {
        method: "POST",
        body: formData,
        credentials: "include",
        headers,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Lỗi HTTP ${response.status}`);
      }

      const result = await response.json();
      if (result.data) {
        onFileUploaded(result.data);
        setProgress(100);
        
        // Reset input after successful upload
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      } else {
        throw new Error("Phản hồi không đúng định dạng");
      }
    } catch (err: any) {
      console.error("Upload error:", err);
      setError(err.message || "Lỗi không xác định khi upload file");
    } finally {
      setUploading(false);
    }
  };

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="w-full">
      <input
        ref={fileInputRef}
        type="file"
        accept={getAcceptString()}
        onChange={handleFileSelect}
        className="hidden"
        disabled={disabled || uploading}
      />

      <Button
        type="button"
        onClick={handleButtonClick}
        disabled={disabled || uploading}
        className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {uploading ? `Đang upload... ${progress}%` : "Chọn file để upload"}
      </Button>

      {uploading && (
        <div className="mt-3">
          <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 text-center">
            {progress < 100 ? "Đang tải lên..." : "Hoàn thành!"}
          </p>
        </div>
      )}

      {error && (
        <div className="mt-3 p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400 text-sm">
          ❌ {error}
        </div>
      )}

      <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        <p>📁 Định dạng: {getAcceptString()}</p>
        <p>📊 Kích thước tối đa: {maxSize}MB</p>
      </div>
    </div>
  );
}