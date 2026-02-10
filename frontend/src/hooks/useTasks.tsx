/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useEffect, useCallback } from "react";
import { Task } from "@/types";
import { taskService, TaskRequest, TaskResponse } from "@/services/taskService";

// Map API response to frontend Task type
function mapTaskResponseToTask(response: TaskResponse): Task {
  return {
    id: response.id,
    title: response.title,
    description: response.description,
    priority: response.priority,
    columnId: response.columnId,
    startDate: response.startDate,
    endDate: response.endDate,
    eventId: response.event?.id,
    event: response.event,
    assignees: response.assignees?.map(a => a.id) || [],
    links: response.links?.map(l => ({
      id: l.id,
      url: l.url,
      title: l.title,
    })) || [],
    createdAt: response.createdAt,
    createdBy: response.createdBy,
    updatedAt: response.updatedAt,
    updatedBy: response.updatedBy,
  };
}

export function useTasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await taskService.getAll();
      const mappedTasks = response.map(mapTaskResponseToTask);
      setTasks(mappedTasks);
    } catch (err: any) {
      setError(err.message || "Failed to fetch tasks");
      console.error("Failed to fetch tasks:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const createTask = async (taskData: TaskRequest, userId: number): Promise<Task> => {
    try {
      const response = await taskService.create(taskData, userId);
      const newTask = mapTaskResponseToTask(response);
      setTasks(prev => [...prev, newTask]);
      return newTask;
    } catch (err: any) {
      throw new Error(err.message || "Failed to create task");
    }
  };

  const updateTask = async (
    taskId: number,
    taskData: TaskRequest,
    userId: number
  ): Promise<Task> => {
    try {
      const response = await taskService.update(taskId, taskData, userId);
      const updatedTask = mapTaskResponseToTask(response);
      setTasks(prev => prev.map(t => (t.id === taskId ? updatedTask : t)));
      return updatedTask;
    } catch (err: any) {
      throw new Error(err.message || "Failed to update task");
    }
  };

  const moveTask = async (
    taskId: number,
    newColumnId: string,
    userId: number
  ): Promise<Task> => {
    try {
      const response = await taskService.move(taskId, newColumnId, userId);
      const movedTask = mapTaskResponseToTask(response);
      setTasks(prev => prev.map(t => (t.id === taskId ? movedTask : t)));
      return movedTask;
    } catch (err: any) {
      throw new Error(err.message || "Failed to move task");
    }
  };

  const deleteTask = async (taskId: number) => {
    try {
      await taskService.delete(taskId);
      setTasks(prev => prev.filter(t => t.id !== taskId));
    } catch (err: any) {
      throw new Error(err.message || "Failed to delete task");
    }
  };

  const getTasksByColumn = useCallback(
    (columnId: string) => {
      return tasks.filter(task => task.columnId === columnId);
    },
    [tasks]
  );

  const getTasksByEvent = useCallback(
    (eventId: number | string) => {
      return tasks.filter(task => task.eventId?.toString() === eventId.toString());
    },
    [tasks]
  );

  return {
    tasks,
    loading,
    error,
    fetchTasks,
    createTask,
    updateTask,
    moveTask,
    deleteTask,
    getTasksByColumn,
    getTasksByEvent,
  };
}