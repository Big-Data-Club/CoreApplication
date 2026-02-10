import { apiClient } from "./api";

export interface UserResponse {
  id: number;
  name: string;
  email: string;
  role: string;
  team: string;
  code: string;
  type: string;
  active: boolean;
  profilePicture?: string;
  totalScore: number;
}

export interface UpdateProfileRequest {
  name: string;
  email: string;
  team?: string;
  type?: string;
  profilePicture?: string;
}

export interface ChangePasswordRequest {
  currentPassword: string;
  newPassword: string;
}

export interface PasswordChangeRequestDto {
  email: string;
  currentPassword: string;
  newPassword: string;
}

export interface ConfirmPasswordChangeRequest {
  token: string;
  newPassword: string;
}

export interface MessageResponse {
  message: string;
}

export interface LoginResponse {
  token: string;
  name: string;
  email: string;
  role: string;
  userId: number;
  maxAge: number;
}

export const userService = {
  getAll: () => apiClient.get<UserResponse[]>("/api/users"),

  login: (email: string, password: string) => {
    const data = apiClient.post<LoginResponse>("/api/auth/login", { email, password });
    return data;
  },

  logout: () => apiClient.post<null>("/api/auth/logout", null),

  // Get user by ID
  getById: (id: number) => apiClient.get<UserResponse>(`/api/users/${id}`),

  // Update user profile
  update: (id: number, data: Partial<UserResponse>) =>
    apiClient.put<UserResponse>(`/api/users/${id}`, data),

  // Update profile (simpler version)
  updateProfile: (id: number, data: UpdateProfileRequest) =>
    apiClient.put<UserResponse>(`/api/users/${id}`, data),

  // OLD METHOD - Đổi password trực tiếp (không qua email)
  changePassword: (userId: number, data: ChangePasswordRequest) =>
    apiClient.post(`/api/users/${userId}/change-password`, data),

  // NEW METHOD - Đổi password với xác nhận qua email
  requestPasswordChange: (data: PasswordChangeRequestDto) =>
    apiClient.post<MessageResponse>("/api/auth/request-password-change", data),

  // NEW METHOD - Xác nhận đổi password với token
  confirmPasswordChange: (data: ConfirmPasswordChangeRequest) =>
    apiClient.post<MessageResponse>("/api/auth/confirm-password-change", data),

  // Delete user
  delete: (id: number) => apiClient.delete(`/api/users/${id}`),

  // Upload profile picture
  uploadProfilePicture: async (userId: number, file: File): Promise<string> => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${apiClient["baseURL"]}/api/users/${userId}/upload-picture`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${document.cookie.split("authToken=")[1]?.split(";")[0]}`,
      },
      body: formData,
    });

    if (!response.ok) {
      throw new Error("Failed to upload profile picture");
    }

    const data = await response.json();
    return data.profilePicture;
  },
};