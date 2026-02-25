import { useState } from "react";
import { Button } from "@/components/ui/button";
import lmsService from "@/services/lmsService";
import { Section } from "@/types";

export function SectionModal({ courseId, section, onClose, onSuccess, existingSections }: {
  courseId: number;
  section: Section | null;
  onClose: () => void;
  onSuccess: () => void;
  existingSections: Section[];
}) {
  const [formData, setFormData] = useState({
    title: section?.title || "",
    description: section?.description || "",
    order_index: section?.order_index ?? existingSections.length + 1,
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      setLoading(true);
      if (section) {
        await lmsService.updateSection(section.id, formData);
      } else {
        await lmsService.createSection(courseId, formData);
      }
      alert(section ? "Cập nhật chương thành công!" : "Tạo chương thành công!");
      onSuccess();
    } catch (error: any) {
      alert(error.response?.data?.error || "Lỗi khi lưu chương");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-2xl w-full">
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold">{section ? "Chỉnh sửa chương" : "Thêm chương mới"}</h2>
        </div>
        <form onSubmit={handleSubmit} className="p-6">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Tên chương *</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className="w-full px-4 py-2 border rounded-lg"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Mô tả</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-2 border rounded-lg"
                rows={3}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Thứ tự</label>
              <input
                type="number"
                value={formData.order_index}
                onChange={(e) => setFormData({ ...formData, order_index: parseInt(e.target.value) })}
                className="w-full px-4 py-2 border rounded-lg"
                min="0"
              />
            </div>
          </div>
          <div className="flex gap-3 mt-6">
            <Button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              {loading ? "Đang lưu..." : section ? "Cập nhật" : "Tạo chương"}
            </Button>
            <Button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
            >
              Hủy
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}