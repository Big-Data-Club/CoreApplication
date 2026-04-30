"use client";

/**
 * usePageContext — global page-context provider for AI Chat Sidebar.
 *
 * Each LMS page calls `setPageContext(...)` to declare what
 * the user is currently viewing. The ChatSidebar reads this
 * context and includes it in every AI request so the engine
 * knows the exact course / section / content without guessing.
 */
import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";

// ── Public interface ────────────────────────────────────────────────────────

export interface PageContext {
  /** High-level category of the current page. */
  pageType:
    | "course_list"
    | "course_detail"
    | "lesson"
    | "quiz"
    | "forum"
    | "dashboard"
    | "other";

  courseId?: number;
  courseName?: string;
  sectionId?: number;
  sectionName?: string;
  contentId?: number;
  contentTitle?: string;
  /** Optional: the actual text content of the lesson/page. */
  contentBody?: string;

  /** Free-form bag for page-specific extras (e.g. quiz id, forum post). */
  extra?: Record<string, any>;
}

// ── Context internals ───────────────────────────────────────────────────────

interface PageContextValue {
  pageContext: PageContext | null;
  setPageContext: (ctx: PageContext) => void;
  patchPageContext: (patch: Partial<PageContext>) => void;
  clearPageContext: () => void;
}

const PageCtx = createContext<PageContextValue | null>(null);

// ── Provider ────────────────────────────────────────────────────────────────

export function PageContextProvider({ children }: { children: ReactNode }) {
  const [pageContext, _setPageContext] = useState<PageContext | null>(null);

  const setPageContext = useCallback((ctx: PageContext) => {
    _setPageContext(ctx);
  }, []);

  const patchPageContext = useCallback((patch: Partial<PageContext>) => {
    _setPageContext((prev) => (prev ? { ...prev, ...patch } : (patch as PageContext)));
  }, []);

  const clearPageContext = useCallback(() => {
    _setPageContext(null);
  }, []);

  return (
    <PageCtx.Provider value={{ pageContext, setPageContext, patchPageContext, clearPageContext }}>
      {children}
    </PageCtx.Provider>
  );
}

// ── Hooks ───────────────────────────────────────────────────────────────────

/** Read the current page context (used by ChatSidebar). */
export function usePageContext(): PageContext | null {
  const ctx = useContext(PageCtx);
  return ctx?.pageContext ?? null;
}

/** Set page context from a page component. */
export function useSetPageContext() {
  const ctx = useContext(PageCtx);
  if (!ctx) {
    // Outside provider — return noops so pages don't crash
    return {
      setPageContext: (_ctx: PageContext) => {},
      patchPageContext: (_patch: Partial<PageContext>) => {},
      clearPageContext: () => {},
    };
  }
  return {
    setPageContext: ctx.setPageContext,
    patchPageContext: ctx.patchPageContext,
    clearPageContext: ctx.clearPageContext,
  };
}
