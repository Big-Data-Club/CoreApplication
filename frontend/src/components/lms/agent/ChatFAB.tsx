"use client";

/**
 * ChatFAB — floating action button to toggle the AI Chat Sidebar.
 *
 * Fixed position, bottom-right. Shows a sparkle icon with a subtle
 * pulse animation. Manages the open/close state of the ChatSidebar.
 *
 * ChatSidebar (~14KB + deps) is lazy-loaded via next/dynamic and
 * preloaded on hover/focus so the first click feels instant.
 */
import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";

// Lazy-load the heavy ChatSidebar — only fetched when FAB is clicked or hovered
const ChatSidebar = dynamic(
  () => import("./ChatSidebar").then((mod) => ({ default: mod.ChatSidebar })),
  { ssr: false },
);

// Preload trigger — call import() once to warm the chunk cache
let _preloaded = false;
function preloadChatSidebar() {
  if (_preloaded) return;
  _preloaded = true;
  import("./ChatSidebar");
}

export function ChatFAB() {
  const [isOpen, setIsOpen] = useState(false);
  // Track if sidebar was ever opened — only mount after first open
  const [hasOpened, setHasOpened] = useState(false);

  const handleToggle = useCallback(() => {
    setIsOpen((prev) => {
      if (!prev) setHasOpened(true);
      return !prev;
    });
  }, []);

  return (
    <>
      {/* Only mount the sidebar after user has opened it at least once */}
      {hasOpened && (
        <ChatSidebar isOpen={isOpen} onClose={() => setIsOpen(false)} />
      )}

      {/* Floating action button */}
      <button
        onClick={handleToggle}
        onMouseEnter={preloadChatSidebar}
        onFocus={preloadChatSidebar}
        className={cn(
          "fixed bottom-6 right-6 z-[62]",
          "w-14 h-14 rounded-full",
          "flex items-center justify-center",
          "shadow-lg shadow-blue-500/25 dark:shadow-blue-500/10",
          "transition-all duration-300 ease-in-out",
          "active:scale-90",
          isOpen
            ? "bg-slate-700 dark:bg-slate-600 hover:bg-slate-800 dark:hover:bg-slate-500 rotate-90"
            : "bg-gradient-to-br from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 rotate-0",
        )}
        title={isOpen ? "Đóng AI Chat" : "Mở AI Chat"}
        aria-label={isOpen ? "Đóng AI Chat" : "Mở AI Chat"}
      >
        {isOpen ? (
          <X className="w-5 h-5 text-white" />
        ) : (
          <>
            <Sparkles className="w-5 h-5 text-white" />
            {/* Pulse ring */}
            <span
              className={cn(
                "absolute inset-0 rounded-full",
                "bg-blue-400/30 dark:bg-blue-400/20",
                "animate-ping",
                "pointer-events-none",
              )}
              style={{ animationDuration: "3s" }}
            />
          </>
        )}
      </button>
    </>
  );
}
