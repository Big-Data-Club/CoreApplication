import { getAccessToken, clearAccessTokenCache } from "./authToken";

export class ApiClient {
  readonly baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }

  private async getHeaders(): Promise<HeadersInit> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "*/*",
    };

    const token = await getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    return headers;
  }

  private async handleResponse<T>(response: Response, endpoint: string): Promise<T> {
    if (response.status === 401) {
      clearAccessTokenCache();
      if (typeof window !== "undefined") {
        const { signOut } = await import("next-auth/react");
        signOut({ callbackUrl: "/login" });
      }
      throw new Error("Unauthorized (401)");
    }

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(`Request to ${endpoint} failed (${response.status})${text ? `: ${text}` : ""}`);
    }

    return response.json();
  }

  async get<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${this.baseURL}${endpoint}`, {
      method: "GET",
      headers: await this.getHeaders(),
      credentials: "include",
    });
    return this.handleResponse<T>(response, endpoint);
  }

  async post<T>(endpoint: string, data: unknown): Promise<T> {
    const response = await fetch(`${this.baseURL}${endpoint}`, {
      method: "POST",
      headers: await this.getHeaders(),
      credentials: "include",
      body: JSON.stringify(data),
    });
    return this.handleResponse<T>(response, endpoint);
  }

  async patch<T>(endpoint: string, data: unknown): Promise<T> {
    const response = await fetch(`${this.baseURL}${endpoint}`, {
      method: "PATCH",
      headers: await this.getHeaders(),
      credentials: "include",
      body: JSON.stringify(data),
    });
    return this.handleResponse<T>(response, endpoint);
  }

  async put<T>(endpoint: string, data: unknown): Promise<T> {
    const response = await fetch(`${this.baseURL}${endpoint}`, {
      method: "PUT",
      headers: await this.getHeaders(),
      credentials: "include",
      body: JSON.stringify(data),
    });
    return this.handleResponse<T>(response, endpoint);
  }

  async delete(endpoint: string): Promise<void> {
    const response = await fetch(`${this.baseURL}${endpoint}`, {
      method: "DELETE",
      headers: await this.getHeaders(),
      credentials: "include",
    });
    if (response.status === 401) {
       clearAccessTokenCache();
       const { signOut } = await import("next-auth/react");
       signOut({ callbackUrl: "/login" });
       return;
    }
    if (!response.ok) {
      throw new Error(`DELETE ${endpoint} failed (${response.status})`);
    }
  }

  async uploadFile<T>(endpoint: string, formData: FormData): Promise<T> {
    const headers: Record<string, string> = {
      Accept: "*/*",
    };

    const token = await getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseURL}${endpoint}`, {
      method: "POST",
      credentials: "include",
      headers,
      body: formData,
    });
    return this.handleResponse<T>(response, endpoint);
  }
}

export const apiClient = new ApiClient("/apiv1");