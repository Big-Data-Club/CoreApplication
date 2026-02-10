"use client";

export function ActionCard({
  icon,
  title,
  description,
  onClick,
  loading,
  badge,
  variant = "default"
}: {
  icon: string;
  title: string;
  description: string;
  onClick: () => void;
  loading?: boolean;
  badge?: number;
  variant?: "default" | "primary" | "success" | "warning" | "info";
}) {
  const variantClasses = {
    default: "border-gray-200 hover:border-gray-300 hover:bg-gray-50",
    primary: "border-blue-200 hover:border-blue-300 hover:bg-blue-50",
    success: "border-green-200 hover:border-green-300 hover:bg-green-50",
    warning: "border-yellow-200 hover:border-yellow-300 hover:bg-yellow-50",
    info: "border-indigo-200 hover:border-indigo-300 hover:bg-indigo-50",
  };

  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`relative p-5 border-2 rounded-xl text-left transition-all duration-200 transform hover:scale-105 hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]}`}
    >
      {badge !== undefined && badge > 0 && (
        <div className="absolute -top-2 -right-2 w-7 h-7 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center shadow-lg">
          {badge > 99 ? "99+" : badge}
        </div>
      )}
      
      <div className="flex items-start gap-4">
        <div className="text-3xl flex-shrink-0">
          {loading ? "⏳" : icon}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-800 mb-1">{title}</h3>
          <p className="text-sm text-gray-600">{description}</p>
        </div>
      </div>
    </button>
  );
}