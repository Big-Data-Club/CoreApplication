"use client";

import React from "react";
import { EventCard } from "./EventCard";
import { LoadingState } from "../LoadingState";
import { EventItem } from "@/types";

interface EventListProps {
  events: EventItem[];
  loading: boolean;
  isAdmin: boolean;
  onView: (event: EventItem) => void;
  onEdit: (event: EventItem) => void;
  onDelete: (id: number) => void;
}

export function EventList({
  events,
  loading,
  isAdmin,
  onView,
  onEdit,
  onDelete,
}: EventListProps) {
  if (loading) {
    return <LoadingState color="border-purple-600" />;
  }

  if (events.length === 0) {
    return (
      <div className="col-span-4 text-center py-12">
        <p className="text-gray-500">Chưa có sự kiện nào</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
      {events.map(event => (
        <EventCard
          key={event.id}
          event={event}
          isAdmin={isAdmin}
          onView={() => onView(event)}
          onEdit={() => onEdit(event)}
          onDelete={() => {
            if (confirm("Bạn có chắc muốn xóa sự kiện này?")) {
              onDelete(event.id);
            }
          }}
        />
      ))}
    </div>
  );
}