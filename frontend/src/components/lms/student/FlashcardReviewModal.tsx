"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ChevronLeft, ChevronRight, BookOpen, Clock, Calendar, ShieldCheck, DatabaseBackup } from "lucide-react";
import { cn } from "@/lib/utils";
import flashcardService, { FlashcardWithRepetition } from "@/services/flashcardService";

interface FlashcardReviewModalProps {
  courseId: number;
  nodeId: number;
  nodeName: string;
  isOpen: boolean;
  onClose: () => void;
}

function getMasteryBadge(item: FlashcardWithRepetition) {
  if (item.repetitions === undefined || item.repetitions === 0) {
    return { label: "Chưa học", color: "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700" };
  }
  const days = item.interval_days || 0;
  if (days <= 3) {
    return { label: "Đang học", color: "bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-950/30 dark:text-orange-400 dark:border-orange-800" };
  }
  if (days <= 7) {
    return { label: "Khá", color: "bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-800" };
  }
  return { label: "Rất tốt", color: "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800" };
}

export function FlashcardReviewModal({ courseId, nodeId, nodeName, isOpen, onClose }: FlashcardReviewModalProps) {
  const [cards, setCards] = useState<FlashcardWithRepetition[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [current, setCurrent] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);

  // ... (useCallback skipped in ReplacementChunk intentionally, wait, replace_file needs exact text or contiguous replacement)

  const loadCards = useCallback(async () => {
    if (!isOpen) return;
    setLoading(true);
    setCurrent(0);
    setIsFlipped(false);
    try {
      const res = await flashcardService.listFlashcards(courseId, nodeId);
      setCards(res.data || []);
      setError("");
    } catch (e: any) {
      setError(e?.response?.data?.message || "Lỗi tải flashcard của chủ đề này.");
    } finally {
      setLoading(false);
    }
  }, [courseId, nodeId, isOpen]);

  useEffect(() => {
    loadCards();
  }, [loadCards]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.body.style.overflow = "hidden";
      document.addEventListener("keydown", handleEsc);
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
      document.removeEventListener("keydown", handleEsc);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleNext = () => {
    if (current < cards.length - 1) {
      setIsFlipped(false);
      setCurrent(c => c + 1);
    }
  };

  const handlePrev = () => {
    if (current > 0) {
      setIsFlipped(false);
      setCurrent(c => c - 1);
    }
  };

  const item = cards[current];
  const noCards = !loading && cards.length === 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-900/40 dark:bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-2xl bg-white dark:bg-slate-900 rounded-2xl shadow-xl flex flex-col max-h-[90vh] mx-4 border border-slate-200 dark:border-slate-800 pointer-events-auto">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-100 dark:bg-violet-950/30 flex items-center justify-center border border-violet-200 dark:border-violet-800">
              <BookOpen className="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 dark:text-slate-50 text-lg">
                Xem lại Flashcard
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                {nodeName}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 flex flex-col overflow-hidden min-h-[400px]">
          {loading ? (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
              <div className="w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full animate-spin mb-4" />
              <p className="text-sm font-medium">Đang tải flashcard...</p>
            </div>
          ) : error ? (
            <div className="flex-1 flex flex-col items-center justify-center text-red-500 px-6 text-center">
              <X className="w-10 h-10 mb-2 opacity-50" />
              <p className="text-sm font-medium">{error}</p>
            </div>
          ) : noCards ? (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 px-6 text-center">
              <DatabaseBackup className="w-12 h-12 mb-4 opacity-20" />
              <p className="text-base font-medium text-slate-700 dark:text-slate-300">Không có flashcard nào</p>
              <p className="text-sm mt-1">Chủ đề này chưa có bất kỳ flashcard nào được tạo.</p>
            </div>
          ) : item ? (
            <div className="flex-1 flex flex-col px-6 py-6 pb-2">
              
              {/* Card count & Meta info */}
              <div className="flex items-center justify-between mb-4 flex-shrink-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-950/30 px-3 py-1 rounded-full border border-violet-100 dark:border-violet-900/50">
                    Thẻ {current + 1} / {cards.length}
                  </span>
                  
                  {(() => {
                    const badge = getMasteryBadge(item);
                    return (
                      <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full border", badge.color)}>
                        {badge.label}
                      </span>
                    );
                  })()}
                </div>

                {item.repetitions !== undefined && item.repetitions > 0 && (
                  <div className="flex gap-2">
                    <span className="flex items-center gap-1.5 text-xs text-slate-500 bg-slate-50 dark:bg-slate-800 px-2 py-1 rounded-md border border-slate-100 dark:border-slate-700">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      Ôn {item.repetitions} lần
                    </span>
                    {item.next_review_date && (
                      <span className="flex items-center gap-1.5 text-xs text-slate-500 bg-slate-50 dark:bg-slate-800 px-2 py-1 rounded-md border border-slate-100 dark:border-slate-700">
                        <Calendar className="w-3.5 h-3.5" />
                        Due {new Date(item.next_review_date).toLocaleDateString("vi-VN")}
                      </span>
                    )}
                  </div>
                )}
                {item.repetitions === undefined || item.repetitions === 0 ? (
                  <span className="flex items-center gap-1 text-xs text-slate-500">
                    <Clock className="w-3.5 h-3.5" /> Chưa ôn lần nào
                  </span>
                ) : null}
              </div>

              {/* The Flip Card */}
              <div className="flex-1 relative perspective-1000 mb-6 flex flex-col justify-center">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={item.id + (isFlipped ? "-back" : "-front")}
                    initial={{ rotateY: isFlipped ? -90 : 90, opacity: 0 }}
                    animate={{ rotateY: 0, opacity: 1 }}
                    exit={{ rotateY: isFlipped ? 90 : -90, opacity: 0 }}
                    transition={{ duration: 0.3 }}
                    className={cn(
                      "w-full h-full max-h-[300px] rounded-3xl p-8 flex flex-col items-center justify-center text-center shadow-sm border border-b-4 cursor-pointer",
                      isFlipped
                        ? "bg-violet-50 dark:bg-violet-900/20 border-violet-200 dark:border-violet-800/80"
                        : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700"
                    )}
                    onClick={() => setIsFlipped(!isFlipped)}
                    style={{ backfaceVisibility: "hidden" }}
                  >
                    {isFlipped ? (
                      <>
                        <p className="text-xs font-semibold text-violet-500 uppercase tracking-widest mb-4">
                          Đáp án
                        </p>
                        <div className="text-lg md:text-xl font-medium text-slate-800 dark:text-slate-100 leading-relaxed overflow-y-auto w-full px-2">
                          {item.back_text}
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4">
                          Câu hỏi / Khái niệm
                        </p>
                        <div className="text-xl md:text-2xl font-bold text-slate-900 dark:text-slate-50 leading-snug w-full px-2">
                          {item.front_text}
                        </div>
                      </>
                    )}
                  </motion.div>
                </AnimatePresence>
              </div>

            </div>
          ) : null}
        </div>

        {/* Footer Navigation */}
        <div className="px-6 py-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 rounded-b-2xl flex items-center justify-between">
          <button
            onClick={handlePrev}
            disabled={current === 0 || noCards}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 border border-transparent shadow-sm disabled:opacity-30 disabled:hover:bg-transparent transition-all"
          >
            <ChevronLeft className="w-4 h-4" /> Trước
          </button>
          
          <div className="text-xs text-slate-500">
            {!noCards && !isFlipped && "Nhấn vào khung để xem đáp án"}
            {!noCards && isFlipped && "Nhấn vào khung để xem lại câu hỏi"}
          </div>

          <button
            onClick={handleNext}
            disabled={current === cards.length - 1 || noCards}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 border border-transparent shadow-sm disabled:opacity-30 disabled:hover:bg-transparent transition-all"
          >
            Tiếp <ChevronRight className="w-4 h-4" />
          </button>
        </div>

      </div>
    </div>
  );
}
