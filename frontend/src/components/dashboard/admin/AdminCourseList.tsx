"use client";

import React, { useState } from "react";
import { Search, Edit2, Trash2, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { Course } from "@/types/course";

interface AdminCourseListProps {
  courses: Course[];
  onDelete: (id: number) => void;
}

export function AdminCourseList({ courses, onDelete }: AdminCourseListProps) {
  const router = useRouter();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");

  const filteredCourses = courses.filter((course) => {
    const matchesSearch = course.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          course.teacher_name?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === "all" || course.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const categories = ["all", ...new Set(courses.map((c) => c.category).filter(Boolean))];

  return (
    <div className="bg-white dark:bg-zinc-900 rounded-3xl p-6 shadow-sm border border-zinc-100 dark:border-zinc-800">
      <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-6 mb-10">
        <div>
          <h3 className="text-xl font-bold text-zinc-900 dark:text-zinc-50">Quản Lý Khóa Học</h3>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1.5 leading-relaxed">Toàn bộ tài liệu và khóa học hiện có</p>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 w-full xl:w-auto">
          {/* Search */}
          <div className="relative group w-full sm:min-w-[320px]">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-400 group-focus-within:text-zinc-900 dark:group-focus-within:text-zinc-100 transition-colors" />
            <input
              type="text"
              placeholder="Tìm theo tiêu đề hoặc giảng viên..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-700/30 rounded-2xl pl-11 pr-4 py-3 
                         text-sm text-zinc-900 dark:text-zinc-50 placeholder:text-zinc-400 focus:bg-white dark:focus:bg-zinc-800 focus:ring-4 focus:ring-zinc-100 dark:focus:ring-zinc-800/50 transition-all outline-none"
            />
          </div>

          {/* Category Filter */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="w-full sm:w-auto bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-700/30 rounded-2xl px-5 py-3 
                       text-sm font-medium text-zinc-900 dark:text-zinc-50 focus:bg-white dark:focus:bg-zinc-800 transition-all outline-none cursor-pointer appearance-none min-w-[160px]"
          >
            <option value="all">Tất cả danh mục</option>
            {categories.filter(c => c !== "all").map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-zinc-100 dark:border-zinc-800">
              <th className="pb-4 pt-0 font-semibold text-zinc-400 text-sm uppercase tracking-wider">Khóa Học</th>
              <th className="pb-4 pt-0 font-semibold text-zinc-400 text-sm uppercase tracking-wider px-4">Giảng Viên</th>
              <th className="pb-4 pt-0 font-semibold text-zinc-400 text-sm uppercase tracking-wider px-4">Danh Mục</th>
              <th className="pb-4 pt-0 font-semibold text-zinc-400 text-sm uppercase tracking-wider px-4 text-center">Trạng Thái</th>
              <th className="pb-4 pt-0 font-semibold text-zinc-400 text-sm uppercase tracking-wider text-right">Thao Tác</th>
            </tr>
          </thead>
          <tbody>
            {filteredCourses.map((course) => (
              <tr 
                key={course.id} 
                className="group hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors border-b border-zinc-50 dark:border-zinc-800/50 last:border-0"
              >
                <td className="py-4 align-middle pr-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-16 bg-zinc-100 dark:bg-zinc-800 rounded-lg overflow-hidden flex-shrink-0 relative border border-zinc-200/50 dark:border-zinc-700/50">
                      {course.thumbnail_url ? (
                        <Image 
                          src={course.thumbnail_url} 
                          alt={course.title} 
                          fill 
                          className="object-cover" 
                          sizes="64px"
                        />
                      ) : (
                        <div className="h-full w-full flex items-center justify-center text-zinc-400 font-bold text-xs uppercase">BDC</div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="font-bold text-zinc-800 dark:text-zinc-100 truncate group-hover:text-blue-500 transition-colors">{course.title}</p>
                      <p className="text-xs text-zinc-400 truncate mt-0.5">ID: {course.id}</p>
                    </div>
                  </div>
                </td>
                <td className="py-4 align-middle px-4 text-sm font-medium text-zinc-600 dark:text-zinc-400 whitespace-nowrap">
                  {course.teacher_name || "Hệ thống"}
                </td>
                <td className="py-4 align-middle px-4">
                  <span className="px-2.5 py-1 bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 rounded-full text-xs font-semibold whitespace-nowrap">
                    {course.category || "General"}
                  </span>
                </td>
                <td className="py-4 align-middle px-4 text-center">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold
                    ${course.status === "PUBLISHED" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${course.status === "PUBLISHED" ? "bg-green-500" : "bg-yellow-500"}`} />
                    {course.status === "PUBLISHED" ? "Đã XB" : "Bản thảo"}
                  </span>
                </td>
                <td className="py-4 align-middle text-right pl-4">
                  <div className="flex items-center justify-end gap-2 p-0.5">
                    <button 
                      onClick={() => router.push(`/lms/teacher/courses/${course.id}`)}
                      className="p-2 hover:bg-blue-100 dark:hover:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-xl transition-all tooltip"
                      title="Vào học/Quản lý"
                    >
                      <ArrowRight className="h-4 w-4" />
                    </button>
                    <button 
                      className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400 rounded-xl transition-all"
                      title="Chỉnh sửa"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button 
                      onClick={() => onDelete(course.id)}
                      className="p-2 hover:bg-red-100 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400 rounded-xl transition-all"
                      title="Xóa"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
