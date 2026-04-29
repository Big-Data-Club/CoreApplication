"use client";

/**
 * useAIIndexPoller — Centralized polling coordinator for AI index status.
 *
 * Problem: Each AIIndexButton used to run its own setInterval polling.
 * With 20 documents, that's 20 requests/6s → rate-limited.
 *
 * Solution: One timer, one batch request for ALL active content IDs.
 *
 * Usage:
 *   <AIIndexPollerProvider>
 *     <AIIndexButton contentId={1} ... />  ← reads from shared state
 *     <AIIndexButton contentId={2} ... />
 *   </AIIndexPollerProvider>
 */

import React, {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { lmsApiClient } from "@/services/lmsApiClient";

// ── Types ────────────────────────────────────────────────────────────────────

type IndexStatus =
  | "not_indexed"
  | "unindexed"
  | "pending"
  | "processing"
  | "indexed"
  | "failed";

interface StatusInfo {
  status: IndexStatus;
  nodes_created: number;
  chunks_created: number;
}

interface PollerContextValue {
  /** Register a content ID to be polled. Call on mount. */
  register: (contentId: number, initialStatus: IndexStatus) => void;
  /** Unregister a content ID. Call on unmount. */
  unregister: (contentId: number) => void;
  /** Get current status for a content ID. */
  getStatus: (contentId: number) => StatusInfo;
  /** Trigger indexing + auto-register for polling. */
  triggerIndex: (contentId: number) => Promise<void>;
  /** Force a single immediate poll (e.g. after trigger). */
  pollNow: () => void;
}

const POLL_INTERVAL_MS = 6000;
const DEFAULT_STATUS: StatusInfo = {
  status: "not_indexed",
  nodes_created: 0,
  chunks_created: 0,
};

// ── Context ──────────────────────────────────────────────────────────────────

const PollerContext = createContext<PollerContextValue | null>(null);

// ── Provider ─────────────────────────────────────────────────────────────────

interface AIIndexPollerProviderProps {
  children: React.ReactNode;
  onIndexed?: (contentId: number) => void;
}

export function AIIndexPollerProvider({
  children,
  onIndexed,
}: AIIndexPollerProviderProps) {
  // Mutable refs for the polling loop (no re-renders)
  const watchSetRef = useRef(new Set<number>());
  const statusMapRef = useRef(new Map<number, StatusInfo>());
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const onIndexedRef = useRef(onIndexed);
  onIndexedRef.current = onIndexed;

  // Reactive state for consumers to re-render
  const [, forceUpdate] = useState(0);
  const triggerRender = useCallback(() => forceUpdate((n) => n + 1), []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // ── Batch poll function ────────────────────────────────────────────────
  const doPoll = useCallback(async () => {
    const activeIds = Array.from(watchSetRef.current);
    if (activeIds.length === 0) return;

    // Only poll IDs that are still "in-flight" (processing/pending)
    const idsToFetch = activeIds.filter((id) => {
      const s = statusMapRef.current.get(id);
      return !s || s.status === "processing" || s.status === "pending";
    });

    // Also fetch IDs that are "indexed" but have no counts yet (initial load)
    const idsNeedingCounts = activeIds.filter((id) => {
      const s = statusMapRef.current.get(id);
      return (
        s?.status === "indexed" &&
        s.nodes_created === 0 &&
        s.chunks_created === 0
      );
    });

    const allIds = [...new Set([...idsToFetch, ...idsNeedingCounts])];
    if (allIds.length === 0) {
      stopTimer();
      return;
    }

    try {
      const res = await lmsApiClient.post<{
        data: Record<string, StatusInfo>;
      }>("/content/batch-ai-index-status", { content_ids: allIds });

      const data = res.data.data;
      let changed = false;

      for (const [idStr, info] of Object.entries(data)) {
        const id = parseInt(idStr, 10);
        const prev = statusMapRef.current.get(id);
        statusMapRef.current.set(id, {
          status: info.status,
          nodes_created: info.nodes_created ?? 0,
          chunks_created: info.chunks_created ?? 0,
        });

        // Detect transitions to terminal state
        if (
          info.status === "indexed" &&
          prev?.status !== "indexed"
        ) {
          onIndexedRef.current?.(id);
        }

        if (prev?.status !== info.status || prev?.nodes_created !== info.nodes_created) {
          changed = true;
        }
      }

      if (changed) triggerRender();
    } catch (err) {
      console.error("[AIIndexPoller] batch poll failed:", err);
    }
  }, [triggerRender, stopTimer]);

  // ── Timer management ───────────────────────────────────────────────────
  const startTimer = useCallback(() => {
    if (timerRef.current) return; // already running
    timerRef.current = setInterval(doPoll, POLL_INTERVAL_MS);
  }, [doPoll]);

  // Cleanup on unmount
  useEffect(() => () => stopTimer(), [stopTimer]);

  // ── Public API ─────────────────────────────────────────────────────────

  const register = useCallback(
    (contentId: number, initialStatus: IndexStatus) => {
      watchSetRef.current.add(contentId);

      // Seed the status map if not already present
      if (!statusMapRef.current.has(contentId)) {
        statusMapRef.current.set(contentId, {
          status: initialStatus,
          nodes_created: 0,
          chunks_created: 0,
        });
      }

      // Start timer if there's anything to watch
      if (watchSetRef.current.size > 0 && !timerRef.current) {
        // Do an immediate poll for this newly registered item,
        // then start the interval
        doPoll();
        startTimer();
      }
    },
    [doPoll, startTimer]
  );

  const unregister = useCallback(
    (contentId: number) => {
      watchSetRef.current.delete(contentId);
      if (watchSetRef.current.size === 0) {
        stopTimer();
      }
    },
    [stopTimer]
  );

  const getStatus = useCallback((contentId: number): StatusInfo => {
    return statusMapRef.current.get(contentId) ?? DEFAULT_STATUS;
  }, []);

  const triggerIndex = useCallback(
    async (contentId: number) => {
      // Optimistically set to processing
      statusMapRef.current.set(contentId, {
        status: "processing",
        nodes_created: 0,
        chunks_created: 0,
      });
      triggerRender();

      // Fire the index request
      await lmsApiClient.post(`/content/${contentId}/ai-index`, {});

      // Make sure we're watching + polling
      watchSetRef.current.add(contentId);
      if (!timerRef.current) startTimer();
    },
    [triggerRender, startTimer]
  );

  const pollNow = useCallback(() => {
    doPoll();
  }, [doPoll]);

  const value: PollerContextValue = {
    register,
    unregister,
    getStatus,
    triggerIndex,
    pollNow,
  };

  return (
    <PollerContext.Provider value={value}>{children}</PollerContext.Provider>
  );
}

// ── Hook for individual buttons ──────────────────────────────────────────────

/**
 * Hook for an individual AIIndexButton to participate in centralized polling.
 * Auto-registers on mount, auto-unregisters on unmount.
 */
export function useAIIndexStatus(
  contentId: number,
  initialStatus: IndexStatus = "not_indexed"
) {
  const ctx = useContext(PollerContext);

  if (!ctx) {
    throw new Error(
      "useAIIndexStatus must be used within <AIIndexPollerProvider>"
    );
  }

  useEffect(() => {
    ctx.register(contentId, initialStatus);
    return () => ctx.unregister(contentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentId]);

  const status = ctx.getStatus(contentId);

  return {
    status: status.status,
    info: status,
    triggerIndex: () => ctx.triggerIndex(contentId),
    pollNow: ctx.pollNow,
  };
}
