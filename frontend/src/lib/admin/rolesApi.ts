import { getAccessToken } from "@/services/authToken";

export interface Role {
  id: number;
  name: string;
  displayName: string;
  description: string;
  isSystem: boolean;
  createdAt: string;
}

export interface Permission {
  id: number;
  resource: string;
  action: string;
  description: string;
}

async function authHeaders(extra?: Record<string, string>): Promise<HeadersInit> {
  const headers: Record<string, string> = { ...extra };
  const token = await getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function fetchRoles(): Promise<Role[]> {
  const res = await fetch(`/apiv1/api/admin/roles`, {
    method: "GET",
    credentials: "include",
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch roles");
  return res.json();
}

export async function createRole(data: { name: string; displayName: string; description?: string }): Promise<Role> {
  const res = await fetch(`/apiv1/api/admin/roles`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create role");
  return res.json();
}

export async function updateRole(id: number, data: { displayName: string; description?: string }): Promise<Role> {
  const res = await fetch(`/apiv1/api/admin/roles/${id}`, {
    method: "PUT",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update role");
  return res.json();
}

export async function deleteRole(id: number): Promise<void> {
  const res = await fetch(`/apiv1/api/admin/roles/${id}`, {
    method: "DELETE",
    credentials: "include",
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete role");
}

export async function fetchPermissions(): Promise<Permission[]> {
  const res = await fetch(`/apiv1/api/admin/permissions`, {
    method: "GET",
    credentials: "include",
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch permissions");
  return res.json();
}

export async function fetchLmsRoleMappings(): Promise<Record<string, string[]>> {
  const res = await fetch(`/apiv1/api/admin/lms-role-mappings`, {
    method: "GET",
    credentials: "include",
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch LMS mappings");
  return res.json();
}

export async function updateLmsRoleMappings(roleId: number, lmsRoles: string[]): Promise<void> {
  const res = await fetch(`/apiv1/api/admin/roles/${roleId}/lms-mappings`, {
    method: "PUT",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify({ lmsRoles }),
  });
  if (!res.ok) throw new Error("Failed to update LMS mappings");
}
