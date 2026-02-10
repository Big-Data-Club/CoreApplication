"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { ChevronDown } from "lucide-react";

interface ShowMoreButtonProps {
  onClick: () => void;
  remaining: number;
  variant: "announcement" | "event";
  customText?: string;
}

export function ShowMoreButton({ 
  onClick, 
  remaining, 
  variant,
  customText 
}: ShowMoreButtonProps) {
  const gradients = {
    announcement: "from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700",
    event: "from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700",
  };

  return (
    <div className="flex justify-center mt-6">
      <Button
        onClick={onClick}
        className={`bg-gradient-to-r ${gradients[variant]} text-white font-semibold px-6 py-3 rounded-xl shadow-lg hover:shadow-xl transition-all group`}
      >
        <span>
          {customText || `Xem thêm ${remaining} ${variant === "announcement" ? "thông báo" : "sự kiện"}`}
        </span>
        <ChevronDown className="ml-2 h-4 w-4 group-hover:translate-y-1 transition-transform" />
      </Button>
    </div>
  );
}