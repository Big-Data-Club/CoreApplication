"use client";

import { useState } from "react";

export function usePagination<T>(items: T[], initialCount: number = 4) {
  const [visibleCount, setVisibleCount] = useState(initialCount);

  const visibleItems = items.slice(0, visibleCount);
  const hasMore = visibleCount < items.length;
  const remaining = items.length - visibleCount;

  function showMore() {
    setVisibleCount(prev => Math.min(prev + 4, items.length));
  }

  function reset() {
    setVisibleCount(initialCount);
  }

  return {
    visibleItems,
    hasMore,
    remaining,
    showMore,
    reset,
  };
}