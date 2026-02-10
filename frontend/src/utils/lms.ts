export function formatCourseLevel(level: string): string {
  const levels: Record<string, string> = {
    BEGINNER: "Cơ bản",
    INTERMEDIATE: "Trung cấp",
    ADVANCED: "Nâng cao",
  };
  return levels[level] || level;
}

export function formatCourseStatus(status: string): string {
  const statuses: Record<string, string> = {
    DRAFT: "Nháp",
    PUBLISHED: "Đã xuất bản",
    ARCHIVED: "Lưu trữ",
  };
  return statuses[status] || status;
}

export function formatEnrollmentStatus(status: string): string {
  const statuses: Record<string, string> = {
    PENDING: "Chờ duyệt",
    APPROVED: "Đã duyệt",
    REJECTED: "Từ chối",
    DROPPED: "Đã hủy",
    COMPLETED: "Hoàn thành",
  };
  return statuses[status] || status;
}

export function getEnrollmentStatusColor(status: string): string {
  const colors: Record<string, string> = {
    PENDING: "bg-yellow-100 text-yellow-800 border-yellow-300",
    APPROVED: "bg-green-100 text-green-800 border-green-300",
    REJECTED: "bg-red-100 text-red-800 border-red-300",
    DROPPED: "bg-gray-100 text-gray-800 border-gray-300",
    COMPLETED: "bg-blue-100 text-blue-800 border-blue-300",
  };
  return colors[status] || "bg-gray-100 text-gray-800 border-gray-300";
}

export function calculateProgress(completed: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((completed / total) * 100);
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function isDeadlineSoon(deadline: string, hoursThreshold: number = 24): boolean {
  const deadlineDate = new Date(deadline);
  const now = new Date();
  const diffHours = (deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60);
  return diffHours <= hoursThreshold && diffHours > 0;
}

export function isDeadlinePassed(deadline: string): boolean {
  return new Date(deadline) < new Date();
}
