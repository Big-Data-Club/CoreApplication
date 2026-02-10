import { apiClient } from "./api";

export interface TaskLinkRequest {
  url: string;
  title: string;
}

export interface TaskRequest {
  title: string;
  description: string;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  columnId: string;
  startDate?: string;
  endDate?: string;
  eventId?: number;
  assigneeIds?: number[];
  links?: TaskLinkRequest[];
}

export interface TaskResponse {
  id: number;
  title: string;
  description: string;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  columnId: 'todo' | 'in-progress' | 'done' | 'cancel';
  startDate?: string;
  endDate?: string;
  event?: {
    id: number;
    title: string;
  };
  assignees: Array<{
    id: number;
    name: string;
    email: string;
    code: string;
    team: string;
    type: string;
  }>;
  links: Array<{
    id: number;
    url: string;
    title: string;
  }>;
  createdAt: string;
  createdBy?: {
    id: number;
    name: string;
    email: string;
  };
  updatedAt?: string;
  updatedBy?: {
    id: number;
    name: string;
    email: string;
  };
}

export const taskService = {
  // Get all tasks
  getAll: () => apiClient.get<TaskResponse[]>("/api/tasks"),

  // Get task by ID
  getById: (id: number) => apiClient.get<TaskResponse>(`/api/tasks/${id}`),

  // Get tasks by event
  getByEvent: (eventId: number) => 
    apiClient.get<TaskResponse[]>(`/api/tasks/event/${eventId}`),

  // Get tasks by column
  getByColumn: (columnId: string) => 
    apiClient.get<TaskResponse[]>(`/api/tasks/column/${columnId}`),

  // Create task
  create: (data: TaskRequest, userId: number) => 
    apiClient.post<TaskResponse>(`/api/tasks?userId=${userId}`, data),

  // Update task
  update: (id: number, data: TaskRequest, userId: number) => 
    apiClient.put<TaskResponse>(`/api/tasks/${id}?userId=${userId}`, data),

  // Move task to different column
  move: (id: number, columnId: string, userId: number) => 
    apiClient.patch<TaskResponse>(`/api/tasks/${id}/move?columnId=${columnId}&userId=${userId}`, {}),

  // Delete task
  delete: (id: number) => 
    apiClient.delete(`/api/tasks/${id}`),

  // Search tasks
  search: (params: {
    keyword?: string;
    columnId?: string;
    priority?: string;
    eventId?: number;
    startAfter?: string;
    endBefore?: string;
    sort?: string[];
  }) => {
    const queryParams = new URLSearchParams();
    
    if (params.keyword) queryParams.append("keyword", params.keyword);
    if (params.columnId) queryParams.append("columnId", params.columnId);
    if (params.priority) queryParams.append("priority", params.priority);
    if (params.eventId) queryParams.append("eventId", params.eventId.toString());
    if (params.startAfter) queryParams.append("startAfter", params.startAfter);
    if (params.endBefore) queryParams.append("endBefore", params.endBefore);
    if (params.sort) {
      params.sort.forEach(s => queryParams.append("sort", s));
    }
    
    return apiClient.get<TaskResponse[]>(`/api/tasks/search?${queryParams.toString()}`);
  }
};