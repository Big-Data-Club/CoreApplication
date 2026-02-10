/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useEffect } from "react";
import { Announcement, ModalMode } from "@/types";
import { announcementService } from "@/services/announcementService";
import { sortByDate } from "@/utils/dateUtils";

export function useAnnouncements() {
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>("add");
  const [currentItem, setCurrentItem] = useState<Partial<Announcement>>({});

  useEffect(() => {
    fetchAnnouncements();
  }, []);

  async function fetchAnnouncements() {
    setLoading(true);
    try {
      const data = await announcementService.getAll();
      setAnnouncements(sortByDate(data));
    } catch (error) {
      console.error("Failed to fetch announcements:", error);
      setAnnouncements([]);
    } finally {
      setLoading(false);
    }
  }

  function openModal(mode: ModalMode, item?: Announcement) {
    setModalMode(mode);
    setCurrentItem(item ? { ...item } : { 
      title: "", 
      content: "", 
      images: [], 
      status: "PENDING" 
    });
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setCurrentItem({});
  }

  async function saveAnnouncement(data: Partial<Announcement>) {
    try {
      let saved: Announcement;
      
      if (modalMode === "add") {
        saved = await announcementService.create(data as Omit<Announcement, "id">);
        setAnnouncements(prev => sortByDate([saved, ...prev]));
      } else if (modalMode === "edit" && data.id) {
        saved = await announcementService.update(data.id, data);
        setAnnouncements(prev => sortByDate(
          prev.map(a => (a.id === saved.id ? saved : a))
        ));
      } else {
        throw new Error("Invalid modal mode or missing announcement ID");
      }
      
      closeModal();
      return saved;
    } catch (error: any) {
      throw new Error(error.message || "Failed to save announcement");
    }
  }

  async function deleteAnnouncement(id: number) {
    try {
      await announcementService.delete(id);
      setAnnouncements(prev => prev.filter(a => a.id !== id));
    } catch (error:any) {
      throw new Error("Failed to delete announcement" + error.message);
    }
  }

  return {
    announcements,
    loading,
    modalOpen,
    modalMode,
    currentItem,
    setCurrentItem,
    openModal,
    closeModal,
    saveAnnouncement,
    deleteAnnouncement,
    refetch: fetchAnnouncements,
  };
}