"use client";

import { useState } from "react";
import forumService, { ForumComment } from "@/services/forumService";
import { Button } from "@/components/ui/button";
import { 
  ThumbsUp, 
  ThumbsDown, 
  MessageSquare, 
  Check,
  Edit,
  Trash2,
  MoreVertical,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { vi } from "date-fns/locale";

interface ForumCommentItemProps {
  comment: ForumComment;
  postId: number;
  onCommentChanged: () => void;
  isPostLocked: boolean;
  isTeacherOrAdmin: boolean;
  postOwnerId: number;
  depth: number;
}

export default function ForumCommentItem({
  comment,
  postId,
  onCommentChanged,
  isPostLocked,
  isTeacherOrAdmin,
  postOwnerId,
  depth,
}: ForumCommentItemProps) {
  const [localComment, setLocalComment] = useState(comment);
  const [voting, setVoting] = useState(false);
  const [showReplyForm, setShowReplyForm] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(comment.body);
  const [showActions, setShowActions] = useState(false);

  const maxDepth = 5;
  const canReply = !isPostLocked && depth < maxDepth;

  const handleVote = async (voteType: 'upvote' | 'downvote') => {
    if (voting) return;
    
    try {
      setVoting(true);
      const response = await forumService.voteComment(localComment.id, voteType);
      
      setLocalComment({
        ...localComment,
        upvotes: response.data.upvotes,
        downvotes: response.data.downvotes,
        score: response.data.new_score,
        current_user_vote: localComment.current_user_vote === voteType ? undefined : voteType,
      });
    } catch (error) {
      console.error("Error voting:", error);
      alert("Không thể vote");
    } finally {
      setVoting(false);
    }
  };

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!replyText.trim()) return;

    try {
      setSubmitting(true);
      await forumService.createComment(postId, {
        body: replyText,
        parent_comment_id: localComment.id,
      });
      setReplyText("");
      setShowReplyForm(false);
      onCommentChanged();
      alert("Đã thêm phản hồi!");
    } catch (error: any) {
      console.error("Error creating reply:", error);
      alert(error.response?.data?.error || "Không thể thêm phản hồi");
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = async () => {
    if (!editText.trim()) return;

    try {
      await forumService.updateComment(localComment.id, editText);
      setLocalComment({ ...localComment, body: editText });
      setEditing(false);
      alert("Đã cập nhật!");
    } catch (error: any) {
      console.error("Error updating comment:", error);
      alert(error.response?.data?.error || "Không thể cập nhật");
    }
  };

  const handleDelete = async () => {
    if (!confirm("Bạn có chắc muốn xóa câu trả lời này?")) return;

    try {
      await forumService.deleteComment(localComment.id);
      alert("Đã xóa");
      onCommentChanged();
    } catch (error) {
      console.error("Error deleting comment:", error);
      alert("Không thể xóa");
    }
  };

  const handleAccept = async () => {
    try {
      await forumService.acceptComment(localComment.id);
      alert("Đã đánh dấu là câu trả lời được chấp nhận!");
      onCommentChanged();
    } catch (error: any) {
      console.error("Error accepting comment:", error);
      alert(error.response?.data?.error || "Không thể thực hiện");
    }
  };

  const getScoreColor = (score: number) => {
    if (score > 0) return "text-green-600";
    if (score < 0) return "text-red-600";
    return "text-gray-600";
  };

  return (
    <div className={`${depth > 0 ? 'ml-8 mt-4' : ''}`}>
      <div className={`border rounded-lg p-4 ${
        localComment.is_accepted ? 'border-green-300 bg-green-50' : 'bg-white'
      }`}>
        <div className="flex gap-4">
          {/* Vote Section */}
          <div className="flex flex-col items-center gap-2">
            <button
              onClick={() => handleVote('upvote')}
              disabled={voting}
              className={`p-1.5 rounded transition-colors ${
                localComment.current_user_vote === 'upvote'
                  ? 'bg-green-100 text-green-600'
                  : 'hover:bg-gray-100 text-gray-400'
              }`}
            >
              <ThumbsUp className="w-4 h-4" />
            </button>
            <span className={`text-sm font-semibold ${getScoreColor(localComment.score)}`}>
              {localComment.score}
            </span>
            <button
              onClick={() => handleVote('downvote')}
              disabled={voting}
              className={`p-1.5 rounded transition-colors ${
                localComment.current_user_vote === 'downvote'
                  ? 'bg-red-100 text-red-600'
                  : 'hover:bg-gray-100 text-gray-400'
              }`}
            >
              <ThumbsDown className="w-4 h-4" />
            </button>
            {localComment.is_accepted && (
              <Check className="w-5 h-5 text-green-600 mt-2" />
            )}
          </div>

          {/* Content Section */}
          <div className="flex-1 min-w-0">
            {/* Meta */}
            <div className="flex items-center gap-2 mb-2">
              <span className="font-semibold text-gray-900">{localComment.user_name}</span>
              <span className="text-xs text-gray-500">
                {formatDistanceToNow(new Date(localComment.created_at), {
                  addSuffix: true,
                  locale: vi,
                })}
              </span>
              {localComment.is_accepted && (
                <span className="flex items-center gap-1 px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded">
                  <Check className="w-3 h-3" />
                  Được chấp nhận
                </span>
              )}
            </div>

            {/* Body */}
            {editing ? (
              <div className="mb-3">
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
                <div className="flex gap-2 mt-2">
                  <Button
                    onClick={handleEdit}
                    size="sm"
                    className="bg-blue-600 text-white hover:bg-blue-700"
                  >
                    Lưu
                  </Button>
                  <Button
                    onClick={() => {
                      setEditing(false);
                      setEditText(localComment.body);
                    }}
                    size="sm"
                    variant="outline"
                  >
                    Hủy
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-gray-700 mb-3 whitespace-pre-wrap">{localComment.body}</p>
            )}

            {/* Actions */}
            <div className="flex items-center gap-3 text-sm">
              {canReply && (
                <button
                  onClick={() => setShowReplyForm(!showReplyForm)}
                  className="flex items-center gap-1 text-gray-600 hover:text-blue-600"
                >
                  <MessageSquare className="w-4 h-4" />
                  Phản hồi
                </button>
              )}

              {/* Accept button (post owner or teacher/admin) */}
              {!localComment.is_accepted && depth === 0 && (isTeacherOrAdmin || postOwnerId === localComment.user_id) && (
                <button
                  onClick={handleAccept}
                  className="flex items-center gap-1 text-green-600 hover:text-green-700"
                >
                  <Check className="w-4 h-4" />
                  Chấp nhận
                </button>
              )}

              <div className="flex-1" />

              {/* More actions */}
              <div className="relative">
                <button
                  onClick={() => setShowActions(!showActions)}
                  className="p-1 hover:bg-gray-100 rounded"
                >
                  <MoreVertical className="w-4 h-4 text-gray-500" />
                </button>

                {showActions && (
                  <>
                    <div
                      className="fixed inset-0 z-10"
                      onClick={() => setShowActions(false)}
                    />
                    <div className="absolute right-0 top-full mt-1 bg-white border rounded-lg shadow-lg py-1 z-20 min-w-[120px]">
                      <button
                        onClick={() => {
                          setEditing(true);
                          setShowActions(false);
                        }}
                        className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 flex items-center gap-2"
                      >
                        <Edit className="w-3 h-3" />
                        Sửa
                      </button>
                      <button
                        onClick={() => {
                          handleDelete();
                          setShowActions(false);
                        }}
                        className="w-full px-3 py-2 text-left text-sm hover:bg-red-50 text-red-600 flex items-center gap-2"
                      >
                        <Trash2 className="w-3 h-3" />
                        Xóa
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Reply Form */}
            {showReplyForm && (
              <form onSubmit={handleReply} className="mt-4 space-y-2">
                <textarea
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Viết phản hồi..."
                  rows={3}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  disabled={submitting}
                />
                <div className="flex gap-2">
                  <Button
                    type="submit"
                    size="sm"
                    disabled={submitting || !replyText.trim()}
                    className="bg-blue-600 text-white hover:bg-blue-700"
                  >
                    {submitting ? "Đang gửi..." : "Gửi"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setShowReplyForm(false);
                      setReplyText("");
                    }}
                  >
                    Hủy
                  </Button>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>

      {/* Nested Replies */}
      {localComment.replies && localComment.replies.length > 0 && (
        <div className="space-y-4">
          {localComment.replies.map((reply) => (
            <ForumCommentItem
              key={reply.id}
              comment={reply}
              postId={postId}
              onCommentChanged={onCommentChanged}
              isPostLocked={isPostLocked}
              isTeacherOrAdmin={isTeacherOrAdmin}
              postOwnerId={postOwnerId}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}