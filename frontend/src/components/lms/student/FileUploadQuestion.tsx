"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Upload, File as FileIcon, CheckCircle, XCircle, AlertCircle, Trash2, Download } from "lucide-react";

interface FileUploadQuestionProps {
  questionId: number;
  value: any; // Current answer value from backend
  onChange: (answerData: any) => void;
  disabled?: boolean;
  maxFileSize?: number; // in MB, default 100MB
  allowedExtensions?: string[]; // e.g., ['.pdf', '.doc', '.docx']
  required?: boolean;
  placeholder?: string;
}

export default function FileUploadQuestion({
  questionId,
  value,
  onChange,
  disabled = false,
  maxFileSize = 100,
  allowedExtensions,
  required = false,
  placeholder = "Chọn file để nộp bài",
}: FileUploadQuestionProps) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [uploadedFile, setUploadedFile] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load existing file from value
  useEffect(() => {
    if (value?.file_name) {
      setUploadedFile({
        file_name: value.file_name,
        file_path: value.file_path,
        file_url: value.file_url,
        file_size: value.file_size,
        file_type: value.file_type || 'document',
      });
    }
  }, [value]);

  const getAcceptString = () => {
    if (allowedExtensions && allowedExtensions.length > 0) {
      return allowedExtensions.join(',');
    }
    // Default: allow common document types
    return ".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.csv,.zip,.rar";
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  };

  const validateFile = (file: File): string | null => {
    // Check file size
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > maxFileSize) {
      return `File quá lớn. Kích thước tối đa: ${maxFileSize}MB`;
    }

    // Check extension if specified
    if (allowedExtensions && allowedExtensions.length > 0) {
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
      if (!allowedExtensions.includes(ext)) {
        return `Định dạng file không được phép. Chỉ chấp nhận: ${allowedExtensions.join(', ')}`;
      }
    }

    return null;
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError("");
    setUploading(true);
    setProgress(0);

    try {
      // Create FormData
      const formData = new FormData();
      formData.append("file", file);
      formData.append("type", "document"); // File upload questions always use "document" type

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
            
            if (response.data) {
              const fileData = {
                file_name: response.data.file_name,
                file_path: response.data.file_path,
                file_url: response.data.file_url,
                file_size: response.data.file_size,
                file_type: response.data.file_type,
                file_id: response.data.file_id,
              };
              
              setUploadedFile(fileData);
              setProgress(100);
              
              // Notify parent component about the upload
              onChange(fileData);
              
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

  const handleRemoveFile = () => {
    setUploadedFile(null);
    setError("");
    setProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    // Notify parent component about removal
    onChange(null);
  };

  const handleDownloadFile = () => {
    if (uploadedFile?.file_url) {
      const apiUrl = process.env.NEXT_PUBLIC_LMS_API_URL || "http://localhost:8081/api/v1";
      const fullUrl = `${apiUrl}${uploadedFile.file_url}`;
      window.open(fullUrl, '_blank');
    }
  };

  return (
    <div className="w-full space-y-4">
      {/* File Input (Hidden) */}
      <input
        ref={fileInputRef}
        type="file"
        accept={getAcceptString()}
        onChange={handleFileSelect}
        className="hidden"
        disabled={disabled || uploading}
      />

      {/* Upload Area */}
      {!uploadedFile ? (
        <div className={`border-2 border-dashed rounded-xl p-6 transition-all ${
          disabled 
            ? 'border-gray-300 bg-gray-50 cursor-not-allowed' 
            : 'border-blue-300 bg-blue-50 hover:border-blue-400 hover:bg-blue-100 cursor-pointer'
        }`}>
          <div className="text-center space-y-3">
            <div className="flex justify-center">
              <Upload className={`w-12 h-12 ${disabled ? 'text-gray-400' : 'text-blue-500'}`} />
            </div>
            
            <div>
              <p className="text-lg font-medium text-gray-700 mb-1">
                {placeholder}
              </p>
              <p className="text-sm text-gray-500">
                Kéo thả file vào đây hoặc click để chọn file
              </p>
            </div>

            <Button
              type="button"
              onClick={handleButtonClick}
              disabled={disabled || uploading}
              className="bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {uploading ? `Đang upload... ${progress}%` : "Chọn File"}
            </Button>

            {/* File Requirements */}
            <div className="text-xs text-gray-500 space-y-1">
              <p>📄 Định dạng: {getAcceptString()}</p>
              <p>📊 Kích thước tối đa: {maxFileSize}MB</p>
              {required && <p className="text-red-600 font-medium">* Bắt buộc phải nộp file</p>}
            </div>
          </div>
        </div>
      ) : (
        // Uploaded File Display
        <div className="border-2 border-green-300 bg-green-50 rounded-xl p-5">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0">
              <div className="w-12 h-12 bg-green-500 rounded-lg flex items-center justify-center">
                <FileIcon className="w-6 h-6 text-white" />
              </div>
            </div>
            
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-900 truncate" title={uploadedFile.file_name}>
                    {uploadedFile.file_name}
                  </p>
                  <p className="text-sm text-gray-600">
                    {formatFileSize(uploadedFile.file_size)}
                  </p>
                </div>
                
                <div className="flex items-center gap-1">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                </div>
              </div>

              <div className="flex items-center gap-2 mt-3">
                <Button
                  type="button"
                  onClick={handleDownloadFile}
                  size="sm"
                  variant="outline"
                  className="text-xs"
                >
                  <Download className="w-3 h-3 mr-1" />
                  Xem file
                </Button>
                
                {!disabled && (
                  <Button
                    type="button"
                    onClick={handleRemoveFile}
                    size="sm"
                    variant="destructive"
                    className="text-xs"
                  >
                    <Trash2 className="w-3 h-3 mr-1" />
                    Xóa
                  </Button>
                  )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Upload Progress */}
      {uploading && (
        <div className="space-y-2">
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-600 text-center">
            {progress < 100 ? "Đang tải lên..." : "Hoàn thành!"}
          </p>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
          <XCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      {/* Required Field Warning */}
      {required && !uploadedFile && !disabled && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <p className="text-amber-700 text-sm">
            <strong>Lưu ý:</strong> Câu hỏi này yêu cầu bạn phải nộp file.
          </p>
        </div>
      )}
    </div>
  );
}