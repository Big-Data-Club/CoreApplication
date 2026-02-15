export type TaskLink = {
  id: number | string;
  url: string;
  title: string;
};

export type Task = {
  id: number | string;
  title: string;
  description: string;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  assignees: (number | string)[]; // Support both number (from API) and string (mock)
  links: TaskLink[];
  startDate?: string;
  endDate?: string;
  columnId: string;
  eventId?: number | string;
  event?: {
    id: number;
    title: string;
  };
  createdAt?: string;
  createdBy?: {
    id: number;
    name: string;
    email: string;
  };
  updatedAt?: string;
  updatedBy?: {
    id: number;
    name: string;
    email: string;
  };
};

export type Team = "RESEARCH" | "ENGINEER" | "EVENT" | "MEDIA";
export type TypeTag = "CLC" | "DT" | "TN";
export type Role = "ROLE_ADMIN" | "ROLE_USER" | "ROLE_MANAGER";

export type User = {
  id: number | string;
  name: string;
  code: string;
  email: string;
  team: Team | string;
  type: TypeTag | string;
  role: Role | string;
  score?: number;
  totalScore?: number;
  dateAdded?: string;
  status?: boolean;
  active?: boolean;
  profilePicture?: string;
};

export type Column = {
  id: string;
  title: string;
  color: string;
  tasks: Task[];
};

export type Announcement = {
  id: number;
  title: string;
  content: string;
  images: string[];
  status: "PENDING" | "APPROVED" | "DENIED" | "EXPIRED";
  createdAt?: string;
  updatedAt?: string;
  createdBy?: string;
};

export type EventItem = {
  id: number;
  title: string;
  description: string;
  statusEvent: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "POSTPONED";
  startTime?: string;
  endTime?: string;
  capacity?: number;
  createdAt?: string;
  updatedAt?: string;
  tasks?: Task[];
};

export type MockEvent = {
  id: number | string;
  text: string;
  start: string;
  end: string;
  backColor?: string;
  participants?: string[];
  ownerId?: string;
  tasks?: Task[];
};

export const ANNOUNCEMENT_STATUSES = ["PENDING", "APPROVED", "DENIED", "EXPIRED"];

export const STATUS_COLORS = {
  PENDING: "bg-yellow-100 text-yellow-800 border-yellow-300",
  IN_PROGRESS: "bg-blue-100 text-blue-800 border-blue-300",
  COMPLETED: "bg-green-100 text-green-800 border-green-300",
  POSTPONED: "bg-gray-100 text-gray-800 border-gray-300",
  APPROVED: "bg-green-100 text-green-800 border-green-300",
  DENIED: "bg-red-100 text-red-800 border-red-300",
  EXPIRED: "bg-gray-100 text-gray-800 border-gray-300",
};

export const PRIORITY_COLORS = {
  LOW: "bg-gray-100 text-gray-800 border-gray-300",
  MEDIUM: "bg-blue-100 text-blue-800 border-blue-300",
  HIGH: "bg-orange-100 text-orange-800 border-orange-300",
  CRITICAL: "bg-red-100 text-red-800 border-red-300",
};

export type ModalMode = "add" | "edit" | "view";

export interface AnnouncementItem {
  id: number;
  title: string;
  content: string;
  type: "INFO" | "WARNING" | "URGENT";
  target: "ALL" | "STUDENT" | "LECTURER";
  createdAt: string;
}

export interface TaskInfo {
  id: number;
  title: string;
  description?: string;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  columnId?: string;
  startDate?: string;
  endDate?: string;
}

export const EVENT_STATUSES = ["PENDING", "IN_PROGRESS", "COMPLETED", "POSTPONED"] as const;

export interface Question {
  id: string;
  type: 'single' | 'multiple' | 'short' | 'long' | 'number' | 'rating' | 
        'date' | 'datetime' | 'time' | 'email' | 'code' | 'fillblank' | 'matching';
  question: string;
  required: boolean;
  note?: string;
  placeholder?: string;
  options?: string[];
  constraints?: {
    min?: number;
    max?: number;
    minChoices?: number;
    maxChoices?: number;
    maxLength?: number;
    step?: number;
  };
  scale?: {
    min: number;
    max: number;
    minLabel?: string;
    maxLabel?: string;
  };
  blanks?: Array<{
    id: string;
    label: string;
    placeholder?: string;
  }>;
  items?: Array<{
    id: string;
    text: string;
  }>;
  categories?: string[];
  language?: string;
  dateType?: 'date' | 'datetime' | 'time';
  correctAnswer?: any;
  points?: number;
}

export interface FormConfig {
  formId: string;
  formTitle: string;
  formDescription: string;
  formType: 'survey' | 'quiz';
  sheetName: string;
  thankYouMessage: string;
  allowMultipleSubmissions: boolean;
  timeLimit?: number;
  passingScore?: number;
  questions: Question[];
}

export interface FormSubmission {
  formId: string;
  formTitle: string;
  sheetName: string;
  formType: string;
  questions: Question[];
  answers: Record<string, any>;
  submittedAt: string;
  userAgent?: string;
  score?: {
    total: number;
    max: number;
    percentage: number;
  };
}

export interface FileToUpload {
  id: string;
  file: File;
  type: "video" | "document" | "image";
  title: string;
  description: string;
  isMandatory: boolean;
  uploadedFile: any | null;
  uploadError: string;
  uploadStatus: "pending" | "uploading" | "success" | "error";
}

export interface Content {
  id: number;
  section_id: number;
  type: string;
  title: string;
  description: string;
  order_index: number;
  is_published: boolean;
  is_mandatory: boolean;
  metadata?: Record<string, any>;
  updated_at?: any;
}

export interface FileInfo {
  file_id: string;
  file_name: string;
  file_url: string;
  file_path: string;
  file_size: number;
  file_type: string;
}

export type ContentType = "TEXT" | "VIDEO" | "DOCUMENT" | "IMAGE" | "QUIZ" | "FORUM" | "ANNOUNCEMENT";

export interface Course {
  id: number;
  title: string;
  description: string;
  status: string;
  level: string;
  category: string;
  thumbnail_url?: string;
  created_at: string;
  published_at?: string;
  teacher_name?: string;
  teacher_email?: string;
}

export interface Section {
  id: number;
  course_id: number;
  title: string;
  description: string;
  order_index: number;
  is_published: boolean;
  created_at: string;
}

export type CourseLevel = 'BEGINNER' | 'INTERMEDIATE' | 'ADVANCED';
export type CourseStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';

export interface CourseSection {
  id: number;
  course_id: number;
  title: string;
  description?: string;
  order_index: number;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContentItem {
  id: number;
  section_id: number;
  type: ContentType;
  title: string;
  description?: string;
  content_url?: string;
  file_size?: number;
  file_type?: string;
  duration_seconds?: number;
  order_index: number;
  is_mandatory: boolean;
  counts_for_progress: boolean;
  points_worth: number;
  requires_previous_completion: boolean;
  available_from?: string;
  available_until?: string;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface Enrollment {
  id: number;
  course_id: number;
  status: 'WAITING' | 'ACCEPTED' | 'REJECTED';
  enrolled_at: string;
  accepted_at?: string;
  rejected_at?: string;
  course_title?: string;
  teacher_name?: string;
  teacher_email?: string;
}

export type TabType = 'discover' | 'my-courses' | 'pending';