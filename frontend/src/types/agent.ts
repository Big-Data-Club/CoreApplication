/**
 * agent.ts
 * TypeScript interfaces for the Multi-Agent Chat system (Phase 4).
 *
 * Maps 1:1 to the backend AgentEvent / AgentEventType enums in
 * ai-service/app/agents/events.py.
 */

// ── SSE Event Types ─────────────────────────────────────────────────────────

export type AgentEventType =
  | "text_delta"
  | "thinking"
  | "tool_start"
  | "tool_result"
  | "ui_component"
  | "clarification"
  | "hitl_request"
  | "session"
  | "title_update"
  | "done"
  | "error";

export interface AgentEvent {
  type: AgentEventType;
  data: Record<string, any>;
  session_id: string;
  turn_id?: string;
}

// ── Chat Messages ───────────────────────────────────────────────────────────

export interface UIComponentData {
  component: string;
  props: Record<string, any>;
}

export interface ClarificationData {
  question: string;
  options: string[];
  missing?: string[];
}

export interface HITLRequestData {
  tool: string;
  message: string;
  data: Record<string, any>;
  ui_instruction?: UIComponentData;
}

export interface ToolActivity {
  tool: string;
  status: "running" | "done" | "error";
  args?: Record<string, any>;
  message?: string;
}

export interface AgentMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  timestamp: number;

  /** Thinking steps emitted during intent/memory phases. */
  thinkingSteps?: { step: string; detail?: string }[];

  /** Tool calls made during this turn. */
  toolActivities?: ToolActivity[];

  /** Dynamic widget injected by tool result. */
  uiComponent?: UIComponentData;

  /** Clarification question from the agent. */
  clarification?: ClarificationData;

  /** HITL approval request (teacher agent only). */
  hitlRequest?: HITLRequestData;
}

// ── Request / Response ──────────────────────────────────────────────────────

export interface AgentChatRequest {
  message: string;
  agent_type: "teacher" | "mentor";
  user_id: number;
  course_id?: number;
  session_id?: string;

  /** Structured in-page context fed by the ChatSidebar. */
  page_context?: Record<string, any>;

  /**
   * Out-of-band system context — used by the Quick Action Panel "Ask AI"
   * button to invisibly inject the current micro-lesson body so the model
   * grounds its answer in the exact lesson the student is reading.
   */
  system_context?: AgentSystemContext;
}

/** Hidden system context for the Quick Action Panel "Ask AI" flow. */
export interface AgentSystemContext {
  lesson_id?: number;
  lesson_title?: string;
  node_id?: number;
  course_id?: number;
  /** Verbatim Markdown body of the active micro-lesson. */
  lesson_text?: string;
}

export interface AgentSession {
  session_id: string;
  title?: string;
  agent_type: "teacher" | "mentor";
  course_id?: number;
  turn_count: number;
  last_active_at?: string;
  created_at?: string;
}

export interface AgentHistoryMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  metadata?: {
    toolActivities?: ToolActivity[];
    uiComponent?: UIComponentData;
    hitlRequest?: HITLRequestData;
  };
  created_at: string;
}
