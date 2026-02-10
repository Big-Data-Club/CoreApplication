"use client";

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Calendar, Clock, MapPin, Eye, Edit, Trash2 } from "lucide-react";
import { EventItem, STATUS_COLORS } from "@/types";
import { getCountdown } from "@/utils/dateUtils";

interface EventCardProps {
  event: EventItem;
  isAdmin: boolean;
  onView: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export function EventCard({
  event,
  isAdmin,
  onView,
  onEdit,
  onDelete,
}: EventCardProps) {
  const countdown = getCountdown(event.startTime, event.endTime);

  return (
    <Card className="overflow-hidden rounded-2xl shadow-lg hover:shadow-2xl transition-all group bg-white border-2 border-gray-100 hover:border-purple-300 transform hover:-translate-y-1">
      <div className="relative w-full h-48 bg-gradient-to-br from-purple-400 via-pink-500 to-red-500 flex items-center justify-center">
        <Calendar className="h-16 w-16 text-white/40" />
        <div className="absolute top-3 right-3">
          <span className={`px-3 py-1 rounded-full text-xs font-bold backdrop-blur-sm ${STATUS_COLORS[event.statusEvent]} border-2`}>
            {event.statusEvent}
          </span>
        </div>
        <div className="absolute bottom-3 left-3 bg-white/90 backdrop-blur-sm px-3 py-1 rounded-lg flex items-center gap-2">
          <Clock className="h-3 w-3 text-purple-600" />
          <span className="text-xs font-semibold text-purple-900">
            {event.startTime ? new Date(event.startTime).toLocaleDateString('vi-VN') : 'Chưa xác định'}
          </span>
        </div>
        {event.capacity && (
          <div className="absolute bottom-3 right-3 bg-white/90 backdrop-blur-sm px-3 py-1 rounded-lg flex items-center gap-2">
            <MapPin className="h-3 w-3 text-purple-600" />
            <span className="text-xs font-semibold text-purple-900">
              {event.capacity} người
            </span>
          </div>
        )}
      </div>
      
      <CardContent className="p-5">
        <h3 className="font-bold text-lg text-gray-800 mb-2 line-clamp-2 group-hover:text-purple-600 transition-colors">
          {event.title}
        </h3>
        <p className="text-sm text-gray-600 line-clamp-3 mb-2">
          {event.description}
        </p>
        {countdown && (
          <p className="text-sm text-purple-600 font-semibold mb-2">
            {countdown}
          </p>
        )}
        
        <div className="flex gap-2 pt-3 border-t border-gray-100">
          <Button 
            size="sm" 
            variant="ghost" 
            onClick={onView}
            className="flex-1 hover:bg-purple-50 rounded-lg transition-all"
          >
            <Eye className="h-4 w-4 mr-1" />
            Xem
          </Button>
          {isAdmin && (
            <>
              <Button 
                size="sm" 
                variant="ghost" 
                onClick={onEdit}
                className="hover:bg-blue-50 rounded-lg transition-all"
              >
                <Edit className="h-4 w-4" />
              </Button>
              <Button 
                size="sm" 
                variant="ghost" 
                onClick={onDelete}
                className="hover:bg-red-50 text-red-600 rounded-lg transition-all"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}