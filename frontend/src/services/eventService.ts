import { EventItem } from "@/types";
import { apiClient } from "./api";

export const eventService = {
  getAll: () => apiClient.get<EventItem[]>("/api/events"),
  
  create: (data: Omit<EventItem, "id">, userId: number) => 
    apiClient.post<EventItem>(`/api/events?userId=${userId}`, data),
  
  update: (id: number, data: Partial<EventItem>) => 
    apiClient.put<EventItem>(`/api/events/${id}`, data),
  
  delete: (id: number) => 
    apiClient.delete(`/api/events/${id}`),
};