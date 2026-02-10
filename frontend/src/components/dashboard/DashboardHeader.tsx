"use client";

import React from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Bell } from "lucide-react";

export function DashboardHeader() {
  return (
    <div className="flex flex-col sm:flex-row md:items-center md:justify-between gap-4 w-full">
      <div>
        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
          Welcome Back! 👋
        </h1>
        <p className="text-gray-600 mt-1">Quản lý sự kiện và thông báo của bạn</p>
      </div>
      <div className="flex flex-row items-center gap-4 w-full md:w-auto md:justify-end">
        <Input 
          placeholder="🔍 Tìm kiếm..." 
          className="rounded-full bg-white shadow-sm w-full md:w-64 focus:ring-2 focus:ring-blue-500 border-2" 
        />
        <div className="relative">
          <Button variant="ghost" size="icon" className="rounded-full hover:bg-blue-100 transition-all">
            <Bell className="h-5 w-5 text-gray-700" />
          </Button>
          <Badge variant="destructive" className="absolute -top-1 -right-1 px-1.5 py-0.5 text-xs rounded-full animate-pulse">
            4
          </Badge>
        </div>
      </div>
    </div>
  );
}