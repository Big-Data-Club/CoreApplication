"use client";

import { ForumComment } from "@/services/forumService";
import ForumCommentItem from "./ForumCommentItem";

interface ForumCommentSectionProps {
  postId: number;
  comments: ForumComment[];
  onCommentChanged: () => void;
  isPostLocked: boolean;
  isTeacherOrAdmin: boolean;
  postOwnerId: number;
}

export default function ForumCommentSection({
  postId,
  comments,
  onCommentChanged,
  isPostLocked,
  isTeacherOrAdmin,
  postOwnerId,
}: ForumCommentSectionProps) {
  if (comments.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <p>Chưa có câu trả lời nào</p>
        <p className="text-sm text-gray-400 mt-1">Hãy là người đầu tiên trả lời!</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {comments.map((comment) => (
        <ForumCommentItem
          key={comment.id}
          comment={comment}
          postId={postId}
          onCommentChanged={onCommentChanged}
          isPostLocked={isPostLocked}
          isTeacherOrAdmin={isTeacherOrAdmin}
          postOwnerId={postOwnerId}
          depth={0}
        />
      ))}
    </div>
  );
}