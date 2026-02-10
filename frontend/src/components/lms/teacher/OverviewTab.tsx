import { Course, Section } from "@/types";

export function OverviewTab({ course, sections }: { course: Course; sections: Section[] }) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-4">Thông tin khóa học</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-600">Trạng thái</p>
            <p className="font-semibold">{course.status === "PUBLISHED" ? "Đã xuất bản" : "Nháp"}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Mức độ</p>
            <p className="font-semibold">{course.level || "Chưa xác định"}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Danh mục</p>
            <p className="font-semibold">{course.category || "Chưa phân loại"}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Số chương</p>
            <p className="font-semibold">{sections.length}</p>
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-semibold mb-4">Danh sách chương</h3>
        {sections.length === 0 ? (
          <p className="text-gray-600">Chưa có chương nào</p>
        ) : (
          <div className="space-y-2">
            {sections.map((section, index) => (
              <div key={section.id} className="p-4 bg-gray-50 rounded-lg">
                <p className="font-medium">
                  Chương {index + 1}: {section.title}
                </p>
                <p className="text-sm text-gray-600">{section.description || "Chưa có mô tả"}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}