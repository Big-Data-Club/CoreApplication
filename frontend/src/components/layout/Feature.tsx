export function Feature({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-9 h-9 rounded-lg bg-white/60 flex items-center justify-center shadow-sm">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M5 12h14" stroke="#6b7280" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M12 5v14" stroke="#6b7280" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </div>
      <div>
        <div className="font-semibold">{title}</div>
        <div className="text-sm text-gray-500">{desc}</div>
      </div>
    </div>
  );
}