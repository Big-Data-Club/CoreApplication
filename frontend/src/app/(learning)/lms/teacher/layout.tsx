"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getCookie } from "@/utils/cookies";
import Link from "next/link";
import { PageContextProvider } from "@/hooks/usePageContext";

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [userName, setUserName] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const selectedRole = sessionStorage.getItem("lms_selected_role");
    if (selectedRole !== "TEACHER" && selectedRole !== "ADMIN") {
      router.push("/lms");
      return;
    }

    const name = getCookie("userName") || "";
    setUserName(name);
    setLoading(false);
  }, [router]);

  const handleChangeRole = () => {
    sessionStorage.removeItem("lms_selected_role");
    router.push("/lms");
  };

  const navItems = [
    { href: "/lms/teacher", label: "Dashboard" },
    { href: "/lms/teacher/courses", label: "Khóa học" },
    { href: "/lms/teacher/ai-assistant", label: "AI Assistant" },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 dark:bg-slate-950">
        <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <PageContextProvider>
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
        <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 shadow-sm sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <div className="flex items-center space-x-3">
                <div>
                  <h1 className="text-xl font-bold text-slate-900 dark:text-slate-50">Giảng viên LMS</h1>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Xin chào, {userName}</p>
                </div>
              </div>

              <nav className="hidden md:flex items-center space-x-1">
                {navItems.map((item) => {
                  const isActive = pathname === item.href ||
                    (item.href !== "/lms/teacher" && pathname.startsWith(item.href));

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${isActive
                          ? "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400"
                          : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-50"
                        }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </nav>

              <div className="flex items-center gap-2">
                <Link
                  href="/"
                  className="px-3 py-2 text-sm text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 rounded-xl hover:text-slate-900 dark:hover:text-slate-50 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                >
                  Trang chủ
                </Link>
                <button
                  onClick={handleChangeRole}
                  className="px-3 py-2 text-sm text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 rounded-xl hover:text-slate-900 dark:hover:text-slate-50 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors font-medium"
                >
                  Đổi vai trò
                </button>
              </div>
            </div>

            <nav className="md:hidden flex items-center space-x-1 pb-3 overflow-x-auto">
              {navItems.map((item) => {
                const isActive = pathname === item.href ||
                  (item.href !== "/lms/teacher" && pathname.startsWith(item.href));

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`px-3 py-1.5 rounded-xl text-sm font-medium whitespace-nowrap transition-colors ${isActive
                        ? "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400"
                        : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                      }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
      </div>
    </PageContextProvider>
  );
}