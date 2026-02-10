/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useEffect } from "react";
import { EventItem, ModalMode } from "@/types";
import { eventService } from "@/services/eventService";
import { sortByDate } from "@/utils/dateUtils";

export function useEvents() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>("add");
  const [currentItem, setCurrentItem] = useState<Partial<EventItem>>({});

  useEffect(() => {
    fetchEvents();
  }, []);

  async function fetchEvents() {
    setLoading(true);
    try {
      const data = await eventService.getAll();
      setEvents(sortByDate(data));
    } catch (error) {
      console.error("Failed to fetch events:", error);
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }

  function openModal(mode: ModalMode, item?: EventItem) {
    setModalMode(mode);
    setCurrentItem(item ? { ...item } : { 
      title: "", 
      description: "", 
      statusEvent: "PENDING",
      startTime: "",
      endTime: "",
      capacity: 0 
    });
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setCurrentItem({});
  }

  async function saveEvent(data: Partial<EventItem>, userId: number) {
    try {
      let saved: EventItem;
      
      if (modalMode === "add") {
        saved = await eventService.create(data as Omit<EventItem, "id">, userId);
        setEvents(prev => sortByDate([saved, ...prev]));
      } else if (modalMode === "edit" && data.id) {
        saved = await eventService.update(data.id, data);
        setEvents(prev => sortByDate(
          prev.map(e => (e.id === saved.id ? saved : e))
        ));
      } else {
        throw new Error("Invalid saved data")
      }
      
      closeModal();
      return saved;
    } catch (error: any) {
      throw new Error(error.message || "Failed to save event");
    }
  }

  async function deleteEvent(id: number) {
    try {
      await eventService.delete(id);
      setEvents(prev => prev.filter(e => e.id !== id));
    } catch (error:any) {
      throw new Error("Failed to delete event" + error.message);
    }
  }

  return {
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
    refetch: fetchEvents,
  };
}