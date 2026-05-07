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

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  newPassword: string;
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

  login: (email: string, password: string) =>
    apiClient.post<LoginResponse>("/api/auth/login", { email, password }),

  logout: () => apiClient.post<null>("/api/auth/logout", null),

  getById: (id: number | string) => apiClient.get<UserResponse>(`/api/users/${id}`),

  update: (id: number | string, data: Partial<UserResponse>) =>
    apiClient.put<UserResponse>(`/api/users/${id}`, data),

  updateProfile: (id: number | string, data: UpdateProfileRequest) =>
    apiClient.put<UserResponse>(`/api/users/${id}`, data),

  changePassword: (userId: number, data: ChangePasswordRequest) =>
    apiClient.post(`/api/users/${userId}/change-password`, data),

  requestPasswordChange: (data: PasswordChangeRequestDto) =>
    apiClient.post<MessageResponse>("/api/auth/request-password-change", data),

  confirmPasswordChange: (data: ConfirmPasswordChangeRequest) =>
    apiClient.post<MessageResponse>("/api/auth/confirm-password-change", data),

  forgotPassword: (email: string) =>
    apiClient.post<MessageResponse>("/api/auth/forgot-password", { email }),

  resetPassword: (data: ResetPasswordRequest) =>
    apiClient.post<MessageResponse>("/api/auth/reset-password", data),

  delete: (id: number) => apiClient.delete(`/api/users/${id}`),

  uploadProfilePicture: async (userId: number | string, file: File): Promise<string> => {
    const formData = new FormData();
    formData.append("file", file);
    // ← fix: dùng uploadFile thay vì hack apiClient["baseURL"] + đọc cookie thủ công
    const data = await apiClient.uploadFile<{ profilePicture: string }>(
      `/api/users/${userId}/upload-picture`,
      formData
    );
    return data.profilePicture;
  },

  // Google OAuth
  googleLogin: (idToken: string) =>
    apiClient.post<any>("/api/auth/google/login", { idToken }).catch((err) => {
      // Handle 404 (user not found) and 403 (pending/blocked) specially
      throw err;
    }),

  googleRegister: (data: {
    idToken: string;
    name: string;
    code: string;
    team: string;
    type: string;
  }) => apiClient.post<{ message: string }>("/api/auth/google/register", data),

  // Admin - Pending users
  getPendingUsers: () => apiClient.get<UserResponse[]>("/api/users/pending"),

  approveUser: (id: number) =>
    apiClient.patch<UserResponse>(`/api/users/${id}/approve`, {}),

  rejectUser: (id: number) =>
    apiClient.patch<UserResponse>(`/api/users/${id}/reject`, {}),
};