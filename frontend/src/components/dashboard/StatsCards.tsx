"use client";

import React from "react";
import { Card } from "@/components/ui/card";
import { Calendar, CheckSquare, Trophy } from "lucide-react";
import { useTasks } from "@/hooks/useTasks";

interface StatsCardsProps {
  eventsCount: number;
}

export function StatsCards({ eventsCount }: StatsCardsProps) {
  const { tasks } = useTasks();

  // Đếm số pending tasks (TODO + In Progress)
  const pendingTasksCount = tasks.filter(
    task => task.columnId === "todo" || task.columnId === "in-progress"
  ).length;

  // Tính overall score (có thể tùy chỉnh logic)
  const completedTasks = tasks.filter(task => task.columnId === "done").length;
  const totalTasks = tasks.length;
  const overallScore = totalTasks > 0 
    ? Math.round((completedTasks / totalTasks) * 100)
    : 0;

  const stats = [
    {
      icon: Calendar,
      value: eventsCount,
      label: "Upcoming Events",
      gradient: "from-blue-500 to-blue-600",
      iconBg: "bg-white/20",
    },
    {
      icon: CheckSquare,
      value: pendingTasksCount,
      label: "Pending Tasks",
      gradient: "from-green-500 to-green-600",
      iconBg: "bg-white/20",
    },
    {
      icon: Trophy,
      value: overallScore,
      label: "Overall Score",
      gradient: "from-yellow-500 to-orange-500",
      iconBg: "bg-white/20",
    },
  ];

  return (
    <div className="flex flex-col gap-2 w-1/3 min-w-[200px]">
      {stats.map((stat, index) => (
        <Card 
          key={index}
          className={`bg-gradient-to-br ${stat.gradient} shadow-lg rounded-xl border-0 hover:scale-[1.02] hover:shadow-xl transition-all transform cursor-pointer p-3`}
        >
          <div className="flex items-center gap-3">
            <div className={`p-2 ${stat.iconBg} backdrop-blur-sm rounded-lg flex-shrink-0`}>
              <stat.icon className="h-6 w-6 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-bold text-white leading-tight">
                {stat.value}
              </h2>
              <p className="text-xs text-white/80 leading-tight">
                {stat.label}
              </p>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}