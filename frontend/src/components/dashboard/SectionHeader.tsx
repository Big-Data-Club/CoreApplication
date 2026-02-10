"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";

interface SectionHeaderProps {
  icon: string;
  title: string;
  description: string;
  showAddButton?: boolean;
  onAdd?: () => void;
  addButtonText?: string;
  addButtonGradient?: string;
}

export function SectionHeader({
  icon,
  title,
  description,
  showAddButton = false,
  onAdd,
  addButtonText = "Thêm",
  addButtonGradient = "from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700",
}: SectionHeaderProps) {
  return (
    <div className="flex justify-between items-center mb-6">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">
          {icon} {title}
        </h2>
        <p className="text-gray-600 text-sm mt-1">{description}</p>
      </div>
      {showAddButton && onAdd && (
        <Button 
          onClick={onAdd}
          className={`bg-gradient-to-r ${addButtonGradient} text-white font-semibold px-6 rounded-xl shadow-lg hover:shadow-xl transition-all`}
        >
          <Plus className="h-4 w-4 mr-2" />
          {addButtonText}
        </Button>
      )}
    </div>
  );
}