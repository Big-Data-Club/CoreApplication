"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import forumService from "@/services/forumService";
import { X } from "lucide-react";

interface ForumCreatePostProps {
  contentId: number;
  onClose: () => void;
  onSuccess: () => void;
}

export default function ForumCreatePost({ contentId, onClose, onSuccess }: ForumCreatePostProps) {
  const [formData, setFormData] = useState({
    title: "",
    body: "",
    tags: "",
  });
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.title || formData.title.length < 5) {
      newErrors.title = "Tiêu đề phải có ít nhất 5 ký tự";
    }
    if (!formData.body || formData.body.length < 10) {
      newErrors.body = "Nội dung phải có ít nhất 10 ký tự";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    try {
      setLoading(true);
      
      const tags = formData.tags
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 0);

      await forumService.createPost(contentId, {
        title: formData.title,
        body: formData.body,
        tags: tags.length > 0 ? tags : undefined,
      });

      alert("Đã tạo bài viết thành công!");
      onSuccess();
    } catch (error: any) {
      console.error("Error creating post:", error);
      alert(error.response?.data?.error || "Không thể tạo bài viết");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="p-6 border-b sticky top-0 bg-white z-10 flex items-center justify-between">
          <h2 className="text-2xl font-bold">Đặt câu hỏi mới</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Tips */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="font-semibold text-blue-900 mb-2">💡 Mẹo viết câu hỏi tốt:</h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Viết tiêu đề rõ ràng, súc tích</li>
              <li>• Mô tả chi tiết vấn đề bạn gặp phải</li>
              <li>• Thêm tags để dễ tìm kiếm</li>
              <li>• Kiểm tra xem câu hỏi đã có ai hỏi chưa</li>
            </ul>
          </div>

          {/* Title */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Tiêu đề <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="vd: Làm thế nào để sử dụng React Hooks?"
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none ${
                errors.title ? 'border-red-500' : ''
              }`}
            />
            {errors.title && (
              <p className="text-red-500 text-sm mt-1">{errors.title}</p>
            )}
          </div>

          {/* Body */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Nội dung chi tiết <span className="text-red-500">*</span>
            </label>
            <textarea
              value={formData.body}
              onChange={(e) => setFormData({ ...formData, body: e.target.value })}
              placeholder="Mô tả chi tiết vấn đề của bạn, những gì bạn đã thử, và kết quả mong muốn..."
              rows={10}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none ${
                errors.body ? 'border-red-500' : ''
              }`}
            />
            {errors.body && (
              <p className="text-red-500 text-sm mt-1">{errors.body}</p>
            )}
            <p className="text-xs text-gray-500 mt-1">
              {formData.body.length} ký tự (tối thiểu 10)
            </p>
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Tags (phân cách bằng dấu phẩy)
            </label>
            <input
              type="text"
              value={formData.tags}
              onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
              placeholder="vd: javascript, react, hooks"
              className="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
            <p className="text-xs text-gray-500 mt-1">
              Tối đa 5 tags, mỗi tag tối đa 50 ký tự
            </p>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t">
            <Button
              type="submit"
              disabled={loading}
              className="flex-1 bg-blue-600 text-white hover:bg-blue-700 py-3"
            >
              {loading ? "Đang tạo..." : "Đăng câu hỏi"}
            </Button>
            <Button
              type="button"
              onClick={onClose}
              variant="outline"
              className="px-6 py-3"
            >
              Hủy
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}