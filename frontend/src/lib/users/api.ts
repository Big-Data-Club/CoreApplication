import { mapServerUserToClient } from "./mappers";
import { User } from "@/types";
import { getAccessToken } from "@/services/authToken";

async function authHeaders(extra?: Record<string, string>): Promise<HeadersInit> {
  const headers: Record<string, string> = { ...extra };
  const token = await getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function fetchUsers(): Promise<User[]> {
  const res = await fetch(`/apiv1/api/users`, {
    method: "GET",
    credentials: "include",
    headers: await authHeaders(),
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(
      `Fetch users failed: ${res.status} ${res.statusText}${txt ? " - " + txt : ""}`
    );
  }

  const data = await res.json();
  if (!Array.isArray(data)) return [];
  return data.map(mapServerUserToClient);
}

export async function postBulkRegister(
  payload: Array<{
    name: string;
    email: string;
    role: string;
    team: string;
    code?: string;
    type: string;
  }>
) {
  const res = await fetch(`/apiv1/api/auth/register/bulk`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify({ users: payload }),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(
      `Bulk register failed: ${res.status} ${res.statusText}${txt ? " - " + txt : ""}`
    );
  }
  return res.json();
}

export async function postCreateUserSingle(user: {
  name: string;
  email: string;
  role: string;
  team: string;
  code: string;
  type: string;
}) {
  return postBulkRegister([user]);
}

export async function updateUser(
  id: number | string,
  data: {
    name: string;
    email: string;
    team?: string;
    type?: string;
  }
): Promise<User> {
  const res = await fetch(`/apiv1/api/users/${id}`, {
    method: "PUT",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(
      `Update user failed: ${res.status} ${res.statusText}${txt ? " - " + txt : ""}`
    );
  }
  const raw = await res.json();
  return mapServerUserToClient(raw);
}

export async function updateUserStatus(id: number | string): Promise<User> {
  const res = await fetch(`/apiv1/api/users/${id}/status`, {
    method: "PATCH",
    credentials: "include",
    headers: await authHeaders(),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(
      `Update status failed: ${res.status} ${res.statusText}${txt ? " - " + txt : ""}`
    );
  }
  const raw = await res.json();
  return mapServerUserToClient(raw);
}

export async function updateUserRole(id: number | string, role: string): Promise<User> {
  const res = await fetch(`/apiv1/api/users/${id}/role`, {
    method: "PATCH",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify({ role }),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(
      `Update role failed: ${res.status} ${res.statusText}${txt ? " - " + txt : ""}`
    );
  }
  const raw = await res.json();
  return mapServerUserToClient(raw);
}