"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import lmsService from "@/services/lmsService";
import { Button } from "@/components/ui/button";
import ContentModal from "@/components/lms/teacher/ContentModal";
import ContentViewer from "@/components/lms/student/ContentViewer";
import BulkUploadModal from "@/components/lms/teacher/BulkUploadModal";
import EditContentModal from "@/components/lms/teacher/EditContentModal";
import { EditCourseModal } from "@/components/lms/teacher/EditCourseModal";
import { SectionModal } from "@/components/lms/teacher/SectionModal";
import { Course, Section } from "@/types";
import { OverviewTab } from "@/components/lms/teacher/OverviewTab";

interface Content {
  id: number;
  section_id: number;
  type: string;
  title: string;
  description: string;
  order_index: number;
  is_published: boolean;
  is_mandatory: boolean;
  metadata?: Record<string, any>;
  file_path?: string;
  file_size?: number;
  file_type?: string;
}

export default function CourseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = parseInt(params.courseId as string);
  
  const [course, setCourse] = useState<Course | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "sections">("overview");
  const [showEditModal, setShowEditModal] = useState(false);
  const [showSectionModal, setShowSectionModal] = useState(false);
  const [editingSection, setEditingSection] = useState<Section | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [showContentModal, setShowContentModal] = useState(false);
  const [selectedSectionId, setSelectedSectionId] = useState<number | null>(null);
  const [sectionContents, setSectionContents] = useState<Record<number, Content[]>>({});
  const [showContentViewer, setShowContentViewer] = useState(false);
  const [selectedContent, setSelectedContent] = useState<Content | null>(null);
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [bulkUploadSectionId, setBulkUploadSectionId] = useState<number | null>(null);
  const [showEditContentModal, setShowEditContentModal] = useState(false);
  const [editingContent, setEditingContent] = useState<Content | null>(null);

  useEffect(() => {
    loadCourse();
    loadSections();
  }, [courseId]);

  const loadCourse = async () => {
    try {
      const data = await lmsService.getCourse(courseId);
      setCourse(data?.data);
    } catch (error) {
      console.error("Error loading course:", error);
      alert("Không tìm thấy khóa học");
      router.push("/lms/teacher/courses");
    }
  };

  const loadSections = async () => {
    try {
      const data = await lmsService.listSections(courseId);
      setSections(data?.data || []);
      setLoading(false);
    } catch (error) {
      console.error("Error loading sections:", error);
      setLoading(false);
    }
  };

  const loadSectionContent = async (sectionId: number) => {
    try {
      const data = await lmsService.listContent(sectionId);
      setSectionContents(prev => ({
        ...prev,
        [sectionId]: data?.data || []
      }));
    } catch (error) {
      console.error("Error loading content:", error);
    }
  };

  const handlePublish = async () => {
    if (!confirm("Bạn có chắc muốn xuất bản khóa học này?")) return;
    
    try {
      await lmsService.publishCourse(courseId);
      alert("Xuất bản khóa học thành công!");
      loadCourse();
    } catch (error: any) {
      alert(error.response?.data?.error || "Lỗi khi xuất bản");
    }
  };

  const toggleSection = (sectionId: number) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(sectionId)) {
      newExpanded.delete(sectionId);
    } else {
      newExpanded.add(sectionId);
      if (!sectionContents[sectionId]) {
        loadSectionContent(sectionId);
      }
    }
    setExpandedSections(newExpanded);
  };

  const handleDeleteSection = async (sectionId: number) => {
    if (!confirm("Bạn có chắc muốn xóa chương này?")) return;
    
    try {
      await lmsService.deleteSection(sectionId);
      alert("Xóa chương thành công!");
      loadSections();
    } catch (error: any) {
      alert(error.response?.data?.error || "Lỗi khi xóa chương");
    }
  };

  const handleDeleteContent = async (contentId: number, sectionId: number) => {
    if (!confirm("Bạn có chắc muốn xóa nội dung này?")) return;
    
    try {
      await lmsService.deleteContent(contentId);
      alert("Xóa nội dung thành công!");
      loadSectionContent(sectionId);
    } catch (error: any) {
      alert(error.response?.data?.error || "Lỗi khi xóa nội dung");
    }
  };

  const getContentTypeIcon = (type: string) => {
    const icons: Record<string, string> = {
      TEXT: "📝",
      VIDEO: "🎥",
      DOCUMENT: "📄",
      IMAGE: "🖼️",
      QUIZ: "❓",
      FORUM: "💬",
      ANNOUNCEMENT: "📢"
    };
    return icons[type] || "📎";
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return "";
    const mb = bytes / (1024 * 1024);
    return mb < 1 ? `${(bytes / 1024).toFixed(1)} KB` : `${mb.toFixed(1)} MB`;
  };

  if (loading || !course) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                course.status === "PUBLISHED" 
                  ? "bg-green-100 text-green-800"
                  : "bg-yellow-100 text-yellow-800"
              }`}>
                {course.status === "PUBLISHED" ? "Xuất bản" : "Nháp"}
              </span>
              {course.level && (
                <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-semibold">
                  {course.level}
                </span>
              )}
              {course.category && (
                <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-xs font-semibold">
                  {course.category}
                </span>
              )}
            </div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">{course.title}</h1>
            <p className="text-gray-600">{course.description || "Chưa có mô tả"}</p>
          </div>
          
          <div className="flex gap-2">
            {course.status === "DRAFT" && (
              <Button
                onClick={handlePublish}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-medium"
              >
                Xuất bản
              </Button>
            )}
            <Button
              onClick={() => setShowEditModal(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Chỉnh sửa
            </Button>
            <Button
              onClick={() => router.push(`/lms/teacher/courses/${courseId}/learners`)}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors font-medium"
            >
              Quản lý học viên
            </Button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-xl shadow-sm border mb-6">
        <div className="border-b px-6">
          <nav className="flex gap-4">
            <Button
              onClick={() => setActiveTab("overview")}
              className={`px-4 py-3 font-medium border-b-2 transition-colors ${
                activeTab === "overview"
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-600 hover:text-gray-900"
              }`}
            >
              Tổng quan
            </Button>
            <Button
              onClick={() => setActiveTab("sections")}
              className={`px-4 py-3 font-medium border-b-2 transition-colors ${
                activeTab === "sections"
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-600 hover:text-gray-900"
              }`}
            >
              Nội dung khóa học
            </Button>
          </nav>
        </div>

        <div className="p-6">
          {activeTab === "overview" && <OverviewTab course={course} sections={sections} />}
          {activeTab === "sections" && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-semibold">Quản lý chương học</h3>
                <div className="flex gap-2">
                  <Button
                    onClick={() => {
                      setEditingSection(null);
                      setShowSectionModal(true);
                    }}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Thêm chương mới
                  </Button>
                </div>
              </div>

              {sections.length === 0 ? (
                <div className="text-center py-12 bg-gray-50 rounded-lg">
                  <p className="text-gray-600 mb-4">Chưa có chương nào</p>
                  <Button
                    onClick={() => setShowSectionModal(true)}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Tạo chương đầu tiên
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  {sections.map((section, index) => (
                    <div key={section.id} className="border rounded-lg overflow-hidden">
                      <div className="p-4 bg-gray-50 flex justify-between items-center">
                        <div className="flex-1">
                          <h4 className="font-semibold">
                            Chương {index + 1}: {section.title}
                          </h4>
                          <p className="text-sm text-gray-600">{section.description || "Chưa có mô tả"}</p>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            onClick={() => toggleSection(section.id)}
                            className="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-100"
                          >
                            {expandedSections.has(section.id) ? "Thu gọn" : "Xem nội dung"}
                          </Button>
                          <Button
                            onClick={() => {
                              setSelectedSectionId(section.id);
                              setShowContentModal(true);
                            }}
                            className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700"
                          >
                            Thêm nội dung
                          </Button>
                          <Button
                            onClick={() => {
                              setBulkUploadSectionId(section.id);
                              setShowBulkUploadModal(true);
                            }}
                            className="px-3 py-1 text-sm bg-purple-600 text-white rounded hover:bg-purple-700"
                          >
                            Bulk Upload
                          </Button>
                          <Button
                            onClick={() => {
                              setEditingSection(section);
                              setShowSectionModal(true);
                            }}
                            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                          >
                            Sửa
                          </Button>
                          <Button
                            onClick={() => handleDeleteSection(section.id)}
                            className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                          >
                            Xóa
                          </Button>
                        </div>
                      </div>

                      {expandedSections.has(section.id) && (
                        <div className="p-4 bg-white border-t">
                          <h5 className="font-medium mb-3">Nội dung trong chương</h5>
                          {!sectionContents[section.id] || sectionContents[section.id].length === 0 ? (
                            <p className="text-gray-600 text-sm">Chưa có nội dung nào</p>
                          ) : (
                            <div className="space-y-2">
                              {sectionContents[section.id].map((content, idx) => (
                                <div key={content.id} className="p-3 bg-gray-50 rounded">
                                  <div className="flex justify-between items-start">
                                    <div className="flex-1">
                                      <p className="font-medium text-sm flex items-center gap-2">
                                        <span>{getContentTypeIcon(content.type)}</span>
                                        <span>{idx + 1}. {content.title}</span>
                                        <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">
                                          {content.type}
                                        </span>
                                        {content.is_mandatory && (
                                          <span className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded">
                                            Bắt buộc
                                          </span>
                                        )}
                                      </p>
                                      <p className="text-xs text-gray-600 mt-1">
                                        {content.description || "Chưa có mô tả"}
                                      </p>
                                      {content.metadata?.file_name && (
                                        <p className="text-xs text-gray-500 mt-1">
                                          📎 {content.metadata.file_name}
                                          {content.metadata.file_size && ` (${formatFileSize(content.metadata.file_size)})`}
                                        </p>
                                      )}
                                    </div>
                                    <div className="flex gap-2">
                                      <Button
                                        onClick={() => {
                                          setSelectedContent(content);
                                          setShowContentViewer(true);
                                        }}
                                        className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                                      >
                                        Xem
                                      </Button>
                                      <Button
                                        onClick={() => {
                                          setEditingContent(content);
                                          setShowEditContentModal(true);
                                        }}
                                        className="px-2 py-1 text-xs bg-orange-600 text-white rounded hover:bg-orange-700"
                                      >
                                        Sửa
                                      </Button>
                                      <Button
                                        onClick={() => handleDeleteContent(content.id, section.id)}
                                        className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                                      >
                                        Xóa
                                      </Button>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {showEditModal && (
        <EditCourseModal
          course={course}
          onClose={() => setShowEditModal(false)}
          onSuccess={() => {
            setShowEditModal(false);
            loadCourse();
          }}
        />
      )}

      {showSectionModal && (
        <SectionModal
          courseId={courseId}
          section={editingSection}
          onClose={() => {
            setShowSectionModal(false);
            setEditingSection(null);
          }}
          onSuccess={() => {
            setShowSectionModal(false);
            setEditingSection(null);
            loadSections();
          }}
          existingSections={sections}
        />
      )}

      {showContentModal && selectedSectionId && (
        <ContentModal
          sectionId={selectedSectionId}
          onClose={() => {
            setShowContentModal(false);
            setSelectedSectionId(null);
          }}
          onSuccess={() => {
            setShowContentModal(false);
            if (selectedSectionId) {
              loadSectionContent(selectedSectionId);
            }
            setSelectedSectionId(null);
          }}
          existingContents={sectionContents[selectedSectionId] || []}
        />
      )}

      {showContentViewer && selectedContent && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b sticky top-0 bg-white z-10 flex justify-between items-center">
              <h2 className="text-xl font-bold">{selectedContent.title}</h2>
              <Button
                onClick={() => {
                  setShowContentViewer(false);
                  setSelectedContent(null);
                }}
                className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
              >
                Đóng
              </Button>
            </div>
            <div className="p-6">
              <ContentViewer content={selectedContent} />
            </div>
          </div>
        </div>
      )}

      {showBulkUploadModal && bulkUploadSectionId && (
        <BulkUploadModal
          sectionId={bulkUploadSectionId}
          onClose={() => {
            setShowBulkUploadModal(false);
            setBulkUploadSectionId(null);
          }}
          onSuccess={() => {
            setShowBulkUploadModal(false);
            setBulkUploadSectionId(null);
            loadSectionContent(bulkUploadSectionId);
          }}
        />
      )}

      {showEditContentModal && editingContent && (
        <EditContentModal
          content={editingContent}
          onClose={() => {
            setShowEditContentModal(false);
            setEditingContent(null);
          }}
          onSuccess={() => {
            setShowEditContentModal(false);
            loadSectionContent(editingContent.section_id);
            setEditingContent(null);
          }}
        />
      )}
    </div>
  );
}