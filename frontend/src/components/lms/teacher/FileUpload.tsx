"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { FileInfo } from "@/types";

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

      // Get auth token from cookie
      const cookies = document.cookie.split(";");
      const authCookie = cookies.find(c => c.trim().startsWith("authToken="));
      const token = authCookie ? authCookie.split("=")[1] : null;

      if (!token) {
        setError("Không tìm thấy token xác thực. Vui lòng đăng nhập lại.");
        setUploading(false);
        return;
      }

      // Upload file with progress tracking
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const percentComplete = Math.round((e.loaded / e.total) * 100);
          setProgress(percentComplete);
        }
      });

      xhr.addEventListener("load", () => {
        if (xhr.status === 200) {
          try {
            const response = JSON.parse(xhr.responseText);
            console.log("Upload response:", response);
            
            if (response.data) {
              onFileUploaded(response.data);
              setProgress(100);
              
              // Reset input after successful upload
              if (fileInputRef.current) {
                fileInputRef.current.value = "";
              }
            } else {
              setError("Phản hồi không đúng định dạng");
            }
          } catch (e) {
            setError("Lỗi khi xử lý phản hồi từ server");
            console.error("Parse error:", e);
          }
        } else {
          try {
            const errorResponse = JSON.parse(xhr.responseText);
            setError(errorResponse.error || `Lỗi HTTP ${xhr.status}`);
          } catch {
            setError(`Lỗi khi upload file (${xhr.status})`);
          }
        }
        setUploading(false);
      });

      xhr.addEventListener("error", () => {
        setError("Lỗi kết nối khi upload file");
        setUploading(false);
        console.error("XHR error");
      });

      xhr.addEventListener("abort", () => {
        setError("Upload đã bị hủy");
        setUploading(false);
      });

      // Use the correct API endpoint
      const apiUrl = process.env.NEXT_PUBLIC_LMS_API_URL || "http://localhost:8081/api/v1";
      xhr.open("POST", `${apiUrl}/files/upload`);
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      
      console.log("Uploading to:", `${apiUrl}/files/upload`);
      xhr.send(formData);

    } catch (err) {
      console.error("Upload error:", err);
      setError("Lỗi không xác định khi upload file");
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
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-600 mt-1 text-center">
            {progress < 100 ? "Đang tải lên..." : "Hoàn thành!"}
          </p>
        </div>
      )}

      {error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          ❌ {error}
        </div>
      )}

      <div className="mt-2 text-xs text-gray-500">
        <p>📁 Định dạng: {getAcceptString()}</p>
        <p>📊 Kích thước tối đa: {maxSize}MB</p>
      </div>
    </div>
  );
}