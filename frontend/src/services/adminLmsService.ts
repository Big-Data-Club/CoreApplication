import { lmsApiClient } from "./lmsApiClient";

export interface UserRoleDetail {
  id: number;
  user_id: number;
  role: string;
  source: "sync" | "manual";
  created_at: string;
}

export interface RoleDefinition {
  id: number;
  name: string;
  display_name: string;
  description: string;
  is_system: boolean;
}

export const adminLmsService = {
  /** Fetch all roles defined in LMS */
  listRoles: async (): Promise<RoleDefinition[]> => {
    const res = await lmsApiClient.get("/admin/roles");
    return res.data;
  },

  /** Fetch LMS roles for a specific user */
  getUserRoles: async (userId: number | string): Promise<UserRoleDetail[]> => {
    const res = await lmsApiClient.get(`/admin/users/${userId}/roles`);
    return res.data;
  },

  /** Assign a role manually to a user */
  assignRole: async (userId: number | string, role: string): Promise<void> => {
    await lmsApiClient.post(`/admin/users/${userId}/roles`, { role });
  },

  /** Remove a manually assigned role from a user */
  removeRole: async (userId: number | string, role: string): Promise<void> => {
    await lmsApiClient.delete(`/admin/users/${userId}/roles/${role}`);
  },
};
