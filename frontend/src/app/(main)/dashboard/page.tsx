"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { StatsCards } from "@/components/dashboard/StatsCards";
import { SectionHeader } from "@/components/dashboard/SectionHeader";
import { AnnouncementList } from "@/components/dashboard/announcement/AnnouncementList";
import { EventList } from "@/components/dashboard/event/EventList";
import { ShowMoreButton } from "@/components/dashboard/ShowMoreButton";
import { AnnouncementModal } from "@/components/dashboard/modals/AnnouncementModal";
import { EventModal } from "@/components/dashboard/modals/EventModal";
import { ModernCalendar as ViewCalendar } from "@/components/dashboard/Calendar";
import { useAnnouncements } from "@/hooks/useAnnouncements";
import { useEvents } from "@/hooks/useEvents";
import { useAuth } from "@/hooks/useAuth";
import { usePagination } from "@/hooks/usePagination";
import TutorialGuide from "@/components/ui/TutorialGuide";
import { tutorialConfig } from "@/config/tutorials";

export default function DashboardPage() {
  const router = useRouter();
  const { user, isAdmin, checkAdminAccess } = useAuth();

  const {
    announcements,
    loading: loadingAnnouncements,
    modalOpen: announcementModalOpen,
    modalMode: announcementModalMode,
    currentItem: currentAnnouncement,
    setCurrentItem: setCurrentAnnouncement,
    openModal: openAnnouncementModal,
    closeModal: closeAnnouncementModal,
    saveAnnouncement,
    deleteAnnouncement,
  } = useAnnouncements();

  const {
    visibleItems: visibleAnnouncements,
    hasMore: hasMoreAnnouncements,
    remaining: remainingAnnouncements,
    showMore: showMoreAnnouncements,
  } = usePagination(announcements, 4);

  const {
    events,
    loading: loadingEvents,
    modalOpen: eventModalOpen,
    modalMode: eventModalMode,
    currentItem: currentEvent,
    setCurrentItem: setCurrentEvent,
    openModal: openEventModal,
    closeModal: closeEventModal,
    saveEvent,
    deleteEvent,
  } = useEvents();

  const {
    visibleItems: visibleEvents,
    hasMore: hasMoreEvents,
    remaining: remainingEvents,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    showMore: _showMoreEvents,
  } = usePagination(events, 4);

  const handleOpenAnnouncementModal = (mode: "add" | "edit" | "view", item?: any) => {
    if (mode === "add" || mode === "edit") {
      if (!checkAdminAccess()) return;
    }
    openAnnouncementModal(mode, item);
  };

  const handleSaveAnnouncement = async () => {
    if (!checkAdminAccess()) return;
    try {
      await saveAnnouncement(currentAnnouncement);
    } catch (error: any) {
      alert("Lỗi: " + error.message);
    }
  };

  const handleDeleteAnnouncement = async (id: number) => {
    if (!checkAdminAccess("xóa")) return;
    try {
      await deleteAnnouncement(id);
    } catch (error: any) {
      alert("Lỗi: " + error.message);
    }
  };

  const handleOpenEventModal = (mode: "add" | "edit" | "view", item?: any) => {
    if (mode === "add" || mode === "edit") {
      if (!checkAdminAccess()) return;
    }
    openEventModal(mode, item);
  };

  const handleSaveEvent = async () => {
    if (!checkAdminAccess() || !user) return;
    try {
      await saveEvent(currentEvent, user.id);
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

  const handleViewAllEvents = () => {
    router.push("/events");
  };

  return (
    <div className="bg-transparent min-h-screen p-4 sm:p-6 lg:p-8">
      {/* Modals */}
      <AnnouncementModal
        open={announcementModalOpen}
        mode={announcementModalMode}
        announcement={currentAnnouncement}
        onOpenChange={closeAnnouncementModal}
        onChange={setCurrentAnnouncement}
        onSave={handleSaveAnnouncement}
      />
      
      <EventModal
        open={eventModalOpen}
        mode={eventModalMode}
        event={currentEvent}
        onOpenChange={closeEventModal}
        onChange={setCurrentEvent}
        onSave={handleSaveEvent}
      />

      <div className="space-y-10">
        {/* Header */}
        <div id="dashboard-header">
          <DashboardHeader />
        </div>

        {/* Stats + Calendar Row */}
        <div className="flex flex-row gap-6 w-full">
          <div id="stats-cards">
            <StatsCards eventsCount={events.length} />
          </div>
          <div className="flex w-full">
            <ViewCalendar />
          </div>
        </div>

        {/* Announcements Section */}
        <div id="announcements-section">
          <SectionHeader
            icon="📢"
            title="Thông Báo"
            description="Các thông báo quan trọng và cập nhật mới nhất"
            showAddButton={isAdmin}
            onAdd={() => handleOpenAnnouncementModal("add")}
            addButtonText="Thêm Thông Báo"
            addButtonGradient="from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700"
          />

          <AnnouncementList
            announcements={visibleAnnouncements}
            loading={loadingAnnouncements}
            isAdmin={isAdmin}
            onView={(item) => handleOpenAnnouncementModal("view", item)}
            onEdit={(item) => handleOpenAnnouncementModal("edit", item)}
            onDelete={handleDeleteAnnouncement}
          />

          {hasMoreAnnouncements && (
            <ShowMoreButton
              onClick={showMoreAnnouncements}
              remaining={remainingAnnouncements}
              variant="announcement"
            />
          )}
        </div>

        {/* Events Section */}
        <div id="events-section">
          <SectionHeader
            icon="🎉"
            title="Sự Kiện"
            description="Các sự kiện sắp diễn ra và đang diễn ra"
            showAddButton={isAdmin}
            onAdd={() => handleOpenEventModal("add")}
            addButtonText="Thêm Sự Kiện"
            addButtonGradient="from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700"
          />

          <EventList
            events={visibleEvents}
            loading={loadingEvents}
            isAdmin={isAdmin}
            onView={(item) => handleOpenEventModal("view", item)}
            onEdit={(item) => handleOpenEventModal("edit", item)}
            onDelete={handleDeleteEvent}
          />

          {hasMoreEvents && (
            <div className="mt-6 flex justify-center">
              <ShowMoreButton
                onClick={handleViewAllEvents}
                remaining={remainingEvents}
                variant="event"
                customText="Xem Tất Cả Sự Kiện"
              />
            </div>
          )}
        </div>
      </div>

      {/* Tutorial Guide Component */}
      <TutorialGuide 
        steps={tutorialConfig.dashboard}
        onComplete={() => {}}
      />
    </div>
  );
}