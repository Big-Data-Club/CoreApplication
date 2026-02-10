"use client";

import { useUser } from "@/store/UserContext";

export function useAuth() {
  const { user } = useUser();

  const isAdmin = user?.role === "ROLE_ADMIN";
  const isManager = user?.role === "ROLE_MANAGER";
  const isAuthenticated = !!user;
  const canEditTask = isAdmin || isManager;

  function checkAdminAccess(action: string = "thực hiện hành động này"): boolean {
    if (!isAdmin) {
      alert(`Chỉ admin mới được ${action}.`);
      return false;
    }
    return true;
  }

  function checkTaskEditAccess(action: string = "chỉnh sửa task"): boolean {
    if (!canEditTask) {
      alert(`Chỉ Admin hoặc Manager mới được ${action}.`);
      return false;
    }
    return true;
  }

  return {
    user,
    isAdmin,
    isManager,
    isAuthenticated,
    canEditTask,
    checkAdminAccess,
    checkTaskEditAccess,
  };
}