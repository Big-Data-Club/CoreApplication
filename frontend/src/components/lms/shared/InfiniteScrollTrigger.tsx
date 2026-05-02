import { useEffect } from "react";
import { useInView } from "@/hooks/useInView";
import { Spinner } from "./Spinner";

export function InfiniteScrollTrigger({
  onLoadMore,
  hasMore,
  loading = false,
}: {
  onLoadMore: () => void;
  hasMore: boolean;
  loading?: boolean;
}) {
  // We use a 400px margin so it loads content before the user even reaches the bottom
  const { ref, isInView } = useInView({ rootMargin: "400px" });

  useEffect(() => {
    if (isInView && hasMore && !loading) {
      onLoadMore();
    }
  }, [isInView, hasMore, loading, onLoadMore]);

  if (!hasMore) return null;

  return (
    <div ref={ref} className="w-full flex items-center justify-center py-6">
      {loading ? <Spinner className="w-6 h-6 text-slate-400" /> : <div className="h-6" />}
    </div>
  );
}
