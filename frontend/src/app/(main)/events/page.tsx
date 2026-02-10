"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EventCard } from "@/components/dashboard/event/EventCard";
import { EventModal } from "@/components/dashboard/modals/EventModal";
import { LoadingState } from "@/components/dashboard/LoadingState";
import { useEvents } from "@/hooks/useEvents";
import { useAuth } from "@/hooks/useAuth";
import { Search, Filter, Calendar, ArrowLeft } from "lucide-react";
import { EVENT_STATUSES } from "@/types";
import { useRouter } from "next/navigation";
import TutorialGuide from '@/components/ui/TutorialGuide';
import { tutorialConfig } from '@/config/tutorials';

export default function EventsPage() {
  const router = useRouter();
  const { isAdmin, checkAdminAccess, user } = useAuth();
  const [searchKeyword, setSearchKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [sortBy, setSortBy] = useState<string>("createdAt:desc");

  const {
    events,
    loading,
    modalOpen,
    modalMode,
    currentItem,
    setCurrentItem,
    openModal,
    closeModal,
    saveEvent,
    deleteEvent,
  } = useEvents();

  const handleOpenModal = (mode: "add" | "edit" | "view", item?: any) => {
    if (mode === "add" || mode === "edit") {
      if (!checkAdminAccess()) return;
    }
    openModal(mode, item);
  };

  const handleSaveEvent = async () => {
    if (!checkAdminAccess() || !user) return;
    try {
      await saveEvent(currentItem, user.id);
    } catch (error: any) {
      alert("Lỗi: " + error.message);
    }
  };

  const handleDeleteEvent = async (id: number) => {
    if (!checkAdminAccess("xóa")) return;
    try {
      await deleteEvent(id);
    } catch (error: any) {
      alert("Lỗi: " + error.message);
    }
  };

  // Filter and sort events
  const filteredEvents = events
    .filter(event => {
      const matchesSearch = !searchKeyword || 
        event.title.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        event.description?.toLowerCase().includes(searchKeyword.toLowerCase());
      
      const matchesStatus = statusFilter === "ALL" || event.statusEvent === statusFilter;
      
      return matchesSearch && matchesStatus;
    })
    .sort((a, b) => {
      const [field, order] = sortBy.split(":");
      const aValue = field === "createdAt" ? new Date(a.startTime || 0).getTime() : a.title;
      const bValue = field === "createdAt" ? new Date(b.startTime || 0).getTime() : b.title;
      
      if (order === "desc") {
        return aValue > bValue ? -1 : 1;
      }
      return aValue > bValue ? 1 : -1;
    });

  return (
    <div className="min-h-screen bg-transparent p-3 sm:p-4 md:p-6 lg:p-8" id="events-page">
      {/* Event Modal */}
      <EventModal
        open={modalOpen}
        mode={modalMode}
        event={currentItem}
        onOpenChange={closeModal}
        onChange={setCurrentItem}
        onSave={handleSaveEvent}
      />

      {/* Header */}
      <div className="mb-6 sm:mb-8" id="events-header">
        <Button
          variant="ghost"
          onClick={() => router.push("/dashboard")}
          className="mb-4 hover:bg-purple-50 text-purple-600"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Quay lại Dashboard
        </Button>
        
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-br from-purple-500 to-pink-500 p-3 rounded-2xl shadow-lg">
              <Calendar className="h-8 w-8 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
                Quản Lý Sự Kiện
              </h1>
              <p className="text-gray-600 mt-1">
                Tất cả các sự kiện trong hệ thống ({filteredEvents.length})
              </p>
            </div>
          </div>
          
          {isAdmin && (
            <Button
              onClick={() => handleOpenModal("add")}
              className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold px-6 rounded-xl shadow-lg hover:shadow-xl transition-all"
            >
              ✨ Thêm Sự Kiện
            </Button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl sm:rounded-2xl shadow-lg p-4 sm:p-6 mb-6 border border-gray-100" id="events-search-filter">
        <div className="flex items-center gap-2 mb-4">
          <Filter className="h-4 w-4 sm:h-5 sm:w-5 text-purple-600" />
          <h2 className="text-base sm:text-lg font-semibold text-gray-800">Bộ Lọc & Tìm Kiếm</h2>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Tìm kiếm sự kiện..."
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              className="pl-10 border-2 border-gray-200 focus:border-purple-400 rounded-xl"
            />
          </div>

          {/* Status Filter */}
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="border-2 border-gray-200 focus:border-purple-400 rounded-xl">
              <SelectValue placeholder="Trạng thái" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">Tất cả trạng thái</SelectItem>
              {EVENT_STATUSES.map(status => (
                <SelectItem key={status} value={status}>
                  {status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Sort */}
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="border-2 border-gray-200 focus:border-purple-400 rounded-xl">
              <SelectValue placeholder="Sắp xếp" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="createdAt:desc">Mới nhất</SelectItem>
              <SelectItem value="createdAt:asc">Cũ nhất</SelectItem>
              <SelectItem value="title:asc">Tên A-Z</SelectItem>
              <SelectItem value="title:desc">Tên Z-A</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Events Grid */}
      <div id="events-grid">
        {loading ? (
          <LoadingState color="border-purple-600" />
        ) : filteredEvents.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center border border-gray-100">
            <Calendar className="h-16 w-16 mx-auto mb-4 text-gray-300" />
            <p className="text-gray-500 text-lg">
              {searchKeyword || statusFilter !== "ALL" 
                ? "Không tìm thấy sự kiện nào"
                : "Chưa có sự kiện nào"}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5 lg:gap-6">
            {filteredEvents.map(event => (
              <EventCard
                key={event.id}
                event={event}
                isAdmin={isAdmin}
                onView={() => handleOpenModal("view", event)}
                onEdit={() => handleOpenModal("edit", event)}
                onDelete={() => {
                  if (confirm("Bạn có chắc muốn xóa sự kiện này?")) {
                    handleDeleteEvent(event.id);
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Tutorial Guide Component */}
      <TutorialGuide 
        steps={tutorialConfig.events}
        onComplete={() => {}}
      />
    </div>
  );
}