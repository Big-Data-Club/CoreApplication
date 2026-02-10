"use client";

import { useState, useEffect } from "react";
import { USER_STORAGE_KEY } from "@/constants";

interface CurrentUser {
  id: number;
  name: string;
  email: string;
  role: string;
}

export function useCurrentUser() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Try to load user from session storage (not localStorage)
    const loadUser = () => {
      try {
        const stored = sessionStorage.getItem(USER_STORAGE_KEY);
        if (stored) {
          setUser(JSON.parse(stored));
        }
      } catch (error) {
        console.error("Failed to load user:", error);
      } finally {
        setLoading(false);
      }
    };

    loadUser();
  }, []);

  const saveUser = (userData: CurrentUser) => {
    try {
      sessionStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData));
      setUser(userData);
    } catch (error) {
      console.error("Failed to save user:", error);
    }
  };

  const clearUser = () => {
    try {
      sessionStorage.removeItem(USER_STORAGE_KEY);
      setUser(null);
    } catch (error) {
      console.error("Failed to clear user:", error);
    }
  };

  return {
    user,
    loading,
    saveUser,
    clearUser,
    userId: user?.id || 1, // Default to 1 for development
  };
}