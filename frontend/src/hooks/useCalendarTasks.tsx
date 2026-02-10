/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useEffect, useCallback } from "react";
import { taskService, TaskResponse } from "@/services/taskService";

type TaskWithColor = TaskResponse & {
  color: string;
  eventName?: string;
  status: 'todo' | 'in-progress' | 'done' | 'cancel';
};

const EVENT_COLORS: { [key: string]: string } = {
  'Data Hackathon 2025': '#8B5CF6',
  'Q4 Planning': '#3B82F6',
  'Research Project': '#10B981',
  'Default': '#9CA3AF',
};

const getEventColor = (): string => {
  // Default colors for common events
  return EVENT_COLORS['Default'];
};

export function useCalendarTasks() {
  const [tasks, setTasks] = useState<TaskWithColor[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await taskService.getAll();
      
      // Map tasks to TaskWithColor format
      const mappedTasks: TaskWithColor[] = response.map(task => ({
        ...task,
        color: getEventColor(),
        eventName: task.event?.title || 'No Event',
        status: task.columnId
      }));

      setTasks(mappedTasks);
    } catch (err: any) {
      setError(err.message || "Failed to fetch tasks");
      console.error("Failed to fetch tasks:", err);
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const refreshTasks = useCallback(() => {
    fetchTasks();
  }, [fetchTasks]);

  return {
    tasks,
    loading,
    error,
    refreshTasks,
  };
}
