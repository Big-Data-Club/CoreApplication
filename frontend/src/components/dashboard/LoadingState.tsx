"use client";

import React from "react";

interface LoadingStateProps {
  color?: string;
  message?: string;
}

export function LoadingState({ 
  color = "border-blue-600", 
  message = "Đang tải..." 
}: LoadingStateProps) {
  return (
    <div className="col-span-4 text-center py-12">
      <div className={`animate-spin rounded-full h-12 w-12 border-b-2 ${color} mx-auto`}></div>
      <p className="text-gray-600 mt-4">{message}</p>
    </div>
  );
}