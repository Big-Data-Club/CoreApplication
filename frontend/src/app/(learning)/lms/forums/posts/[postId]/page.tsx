"use client";

import { useParams, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import lmsService from "@/services/lmsService";
import ForumPostDetail from "@/components/lms/forum/ForumPostDetail";

export default function PostDetailPage() {
  const params = useParams();
  const router = useRouter();
  const postId = parseInt(params.postId as string);
  
  const [roles, setRoles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadUserRoles();
  }, []);

  const loadUserRoles = async () => {
    try {
      const userRoles = await lmsService.getMyRoles();
      setRoles(userRoles || []);
    } catch (error) {
      console.error("Error loading roles:", error);
      setRoles([]);
    } finally {
      setLoading(false);
    }
  };

  const isTeacherOrAdmin = roles.includes("TEACHER") || roles.includes("ADMIN");

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <ForumPostDetail 
        postId={postId} 
        isTeacherOrAdmin={isTeacherOrAdmin}
      />
    </div>
  );
}