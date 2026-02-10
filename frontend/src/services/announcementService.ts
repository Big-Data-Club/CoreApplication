import { Announcement } from "@/types";
import { apiClient } from "./api";

export const announcementService = {
  getAll: () => apiClient.get<Announcement[]>("/api/announcements"),
  
  create: (data: Omit<Announcement, "id">) => 
    apiClient.post<Announcement>("/api/announcements", data),
  
  update: (id: number, data: Partial<Announcement>) => 
    apiClient.put<Announcement>(`/api/announcements/${id}`, data),
  
  delete: (id: number) => 
    apiClient.delete(`/api/announcements/${id}`),
};