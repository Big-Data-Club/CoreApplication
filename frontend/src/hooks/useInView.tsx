"use client";

import { useState, useEffect, useRef, useCallback } from "react";

/**
 * useInView — Intersection Observer hook for lazy rendering.
 *
 * Returns a ref callback and an `isInView` boolean.
 * Once the element enters the viewport, `isInView` becomes true
 * and stays true (one-shot trigger — never reverts to false).
 *
 * Usage:
 *   const { ref, isInView } = useInView({ rootMargin: "200px" });
 *   return <div ref={ref}>{isInView && <HeavyComponent />}</div>;
 */
export function useInView(options?: IntersectionObserverInit) {
  const [isInView, setIsInView] = useState(false);
  const elementRef = useRef<Element | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const ref = useCallback(
    (node: Element | null) => {
      // Clean up previous observer
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }

      // If already triggered, no need to observe again
      if (isInView) return;

      elementRef.current = node;

      if (!node) return;

      observerRef.current = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            setIsInView(true);
            // Once seen, disconnect — one-shot
            observerRef.current?.disconnect();
            observerRef.current = null;
          }
        },
        {
          threshold: 0,
          rootMargin: "200px", // start loading 200px before element is visible
          ...options,
        },
      );

      observerRef.current.observe(node);
    },
    [isInView, options],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  return { ref, isInView };
}
