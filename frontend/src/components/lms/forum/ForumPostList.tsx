"use client";

import { ForumPost } from "@/services/forumService";
import ForumPostCard from "./ForumPostCard";

interface ForumPostListProps {
  posts: ForumPost[];
  onPostDeleted: () => void;
  isTeacherOrAdmin: boolean;
}

export default function ForumPostList({ posts, onPostDeleted, isTeacherOrAdmin }: ForumPostListProps) {
  return (
    <div className="space-y-3">
      {posts.map((post) => (
        <ForumPostCard
          key={post.id}
          post={post}
          onPostDeleted={onPostDeleted}
          isTeacherOrAdmin={isTeacherOrAdmin}
        />
      ))}
    </div>
  );
}