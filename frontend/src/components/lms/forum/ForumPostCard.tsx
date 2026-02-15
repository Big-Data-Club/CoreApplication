"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ForumPost } from "@/services/forumService";
import forumService from "@/services/forumService";
import { 
  ThumbsUp, 
  ThumbsDown, 
  MessageSquare, 
  Eye, 
  Pin, 
  Lock,
  Edit,
  Trash2,
  MoreVertical 
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatDistanceToNow } from "date-fns";
import { vi } from "date-fns/locale";

interface ForumPostCardProps {
  post: ForumPost;
  onPostDeleted: () => void;
  isTeacherOrAdmin: boolean;
}

export default function ForumPostCard({ post, onPostDeleted, isTeacherOrAdmin }: ForumPostCardProps) {
  const router = useRouter();
  const [localPost, setLocalPost] = useState(post);
  const [voting, setVoting] = useState(false);
  const [showActions, setShowActions] = useState(false);

  const handleVote = async (voteType: 'upvote' | 'downvote') => {
    if (voting) return;
    
    try {
      setVoting(true);
      const response = await forumService.votePost(localPost.id, voteType);
      
      // Update local state
      setLocalPost({
        ...localPost,
        upvotes: response.data.upvotes,
        downvotes: response.data.downvotes,
        score: response.data.new_score,
        current_user_vote: localPost.current_user_vote === voteType ? undefined : voteType,
      });
    } catch (error) {
      console.error("Error voting:", error);
      alert("Không thể vote");
    } finally {
      setVoting(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Bạn có chắc muốn xóa bài viết này?")) return;

    try {
      await forumService.deletePost(localPost.id);
      alert("Đã xóa bài viết");
      onPostDeleted();
    } catch (error) {
      console.error("Error deleting post:", error);
      alert("Không thể xóa bài viết");
    }
  };

  const handlePin = async () => {
    try {
      await forumService.pinPost(localPost.id, !localPost.is_pinned);
      setLocalPost({ ...localPost, is_pinned: !localPost.is_pinned });
      alert(localPost.is_pinned ? "Đã bỏ ghim" : "Đã ghim bài viết");
    } catch (error) {
      console.error("Error pinning post:", error);
      alert("Không thể thực hiện");
    }
  };

  const handleLock = async () => {
    try {
      await forumService.lockPost(localPost.id, !localPost.is_locked);
      setLocalPost({ ...localPost, is_locked: !localPost.is_locked });
      alert(localPost.is_locked ? "Đã mở khóa" : "Đã khóa bài viết");
    } catch (error) {
      console.error("Error locking post:", error);
      alert("Không thể thực hiện");
    }
  };

  const getScoreColor = (score: number) => {
    if (score > 0) return "text-green-600";
    if (score < 0) return "text-red-600";
    return "text-gray-600";
  };

  return (
    <div
      className={`bg-white rounded-lg border p-4 hover:shadow-md transition-shadow cursor-pointer ${
        localPost.is_pinned ? 'border-blue-300 bg-blue-50' : ''
      }`}
      onClick={() => router.push(`/lms/forums/posts/${localPost.id}`)}
    >
      <div className="flex gap-4">
        {/* Vote Section */}
        <div className="flex flex-col items-center gap-2 min-w-[60px]">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleVote('upvote');
            }}
            disabled={voting}
            className={`p-2 rounded-lg transition-colors ${
              localPost.current_user_vote === 'upvote'
                ? 'bg-green-100 text-green-600'
                : 'hover:bg-gray-100 text-gray-400'
            }`}
          >
            <ThumbsUp className="w-5 h-5" />
          </button>
          <span className={`text-lg font-bold ${getScoreColor(localPost.score)}`}>
            {localPost.score}
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleVote('downvote');
            }}
            disabled={voting}
            className={`p-2 rounded-lg transition-colors ${
              localPost.current_user_vote === 'downvote'
                ? 'bg-red-100 text-red-600'
                : 'hover:bg-gray-100 text-gray-400'
            }`}
          >
            <ThumbsDown className="w-5 h-5" />
          </button>
        </div>

        {/* Content Section */}
        <div className="flex-1 min-w-0">
          {/* Title and Badges */}
          <div className="flex items-start gap-2 mb-2">
            {localPost.is_pinned && (
              <Pin className="w-4 h-4 text-blue-600 flex-shrink-0 mt-1" />
            )}
            {localPost.is_locked && (
              <Lock className="w-4 h-4 text-orange-600 flex-shrink-0 mt-1" />
            )}
            <h3 className="text-lg font-semibold text-gray-900 hover:text-blue-600 flex-1">
              {localPost.title}
            </h3>
          </div>

          {/* Body Preview */}
          <p className="text-gray-600 text-sm mb-3 line-clamp-2">
            {localPost.body}
          </p>

          {/* Tags */}
          {localPost.tags && localPost.tags.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {localPost.tags.map((tag, index) => (
                <span
                  key={index}
                  className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded"
                  onClick={(e) => e.stopPropagation()}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Meta Info */}
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <div className="flex items-center gap-1">
              <MessageSquare className="w-4 h-4" />
              <span>{localPost.comment_count} câu trả lời</span>
            </div>
            <div className="flex items-center gap-1">
              <Eye className="w-4 h-4" />
              <span>{localPost.view_count} lượt xem</span>
            </div>
            <div className="flex-1" />
            <span>
              bởi <strong>{localPost.user_name}</strong>
            </span>
            <span>
              {formatDistanceToNow(new Date(localPost.created_at), {
                addSuffix: true,
                locale: vi,
              })}
            </span>
          </div>
        </div>

        {/* Actions Menu */}
        {isTeacherOrAdmin && (
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowActions(!showActions);
              }}
              className="p-2 hover:bg-gray-100 rounded-lg"
            >
              <MoreVertical className="w-5 h-5 text-gray-500" />
            </button>

            {showActions && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowActions(false);
                  }}
                />
                <div className="absolute right-0 top-full mt-1 bg-white border rounded-lg shadow-lg py-1 z-20 min-w-[150px]">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handlePin();
                      setShowActions(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 flex items-center gap-2"
                  >
                    <Pin className="w-4 h-4" />
                    {localPost.is_pinned ? 'Bỏ ghim' : 'Ghim bài viết'}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleLock();
                      setShowActions(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 flex items-center gap-2"
                  >
                    <Lock className="w-4 h-4" />
                    {localPost.is_locked ? 'Mở khóa' : 'Khóa bài viết'}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete();
                      setShowActions(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-red-50 text-red-600 flex items-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" />
                    Xóa
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}