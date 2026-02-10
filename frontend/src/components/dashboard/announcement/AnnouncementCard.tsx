"use client";

import React from "react";
import Image from "next/image";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Bell, Eye, Edit, Trash2 } from "lucide-react";
import { Announcement, STATUS_COLORS } from "@/types";

interface AnnouncementCardProps {
  announcement: Announcement;
  isAdmin: boolean;
  onView: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export function AnnouncementCard({
  announcement,
  isAdmin,
  onView,
  onEdit,
  onDelete,
}: AnnouncementCardProps) {
  return (
    <Card className="overflow-hidden rounded-2xl shadow-lg hover:shadow-2xl transition-all group bg-white border-2 border-gray-100 hover:border-blue-300 transform hover:-translate-y-1">
      {announcement.images?.[0] ? (
        <div className="relative w-full h-48 overflow-hidden">
          <Image 
            src={announcement.images[0]} 
            alt={announcement.title} 
            fill 
            style={{ objectFit: "cover" }} 
            className="group-hover:scale-110 transition-transform duration-300"
          />
          <div className="absolute top-3 right-3">
            <span className={`px-3 py-1 rounded-full text-xs font-bold backdrop-blur-sm ${STATUS_COLORS[announcement.status]} border-2`}>
              {announcement.status}
            </span>
          </div>
        </div>
      ) : (
        <div className="relative w-full h-48 bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center">
          <Bell className="h-16 w-16 text-white/40" />
          <div className="absolute top-3 right-3">
            <span className={`px-3 py-1 rounded-full text-xs font-bold backdrop-blur-sm ${STATUS_COLORS[announcement.status]} border-2`}>
              {announcement.status}
            </span>
          </div>
        </div>
      )}
      
      <CardContent className="p-5">
        <h3 className="font-bold text-lg text-gray-800 mb-2 line-clamp-2 group-hover:text-blue-600 transition-colors">
          {announcement.title}
        </h3>
        <p className="text-sm text-gray-600 line-clamp-3 mb-4">
          {announcement.content}
        </p>

        <div className="flex gap-2 pt-3 border-t border-gray-100">
          <Button 
            size="sm" 
            variant="ghost" 
            onClick={onView}
            className="flex-1 hover:bg-blue-50 rounded-lg transition-all"
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
                className="hover:bg-purple-50 rounded-lg transition-all"
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