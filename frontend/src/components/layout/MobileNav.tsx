"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { signOut } from "next-auth/react";
import { Menu, LogOut, Sun, Moon, Settings } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { sidebarSections, LogoIcon } from "@/constants";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { useUser } from "@/store/UserContext";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "next-themes";
import SafeImage from "../common/SafeImage";

const MobileNav = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { user, setUser } = useUser();
  const { isAdmin } = useAuth();
  const { theme, setTheme } = useTheme();
  const [isOpen, setIsOpen] = useState(false);

  const handleLogout = async () => {
    setUser(null);
    await signOut({ callbackUrl: "/login" });
    setIsOpen(false);
  };

  return (
    <header className="flex md:hidden items-center h-14 px-3 sticky top-0 z-50
                       bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
      <Sheet open={isOpen} onOpenChange={setIsOpen}>
        <SheetTrigger asChild>
          <button className="p-2 rounded-xl text-slate-600 dark:text-slate-400
                             hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            <Menu className="h-5 w-5" />
            <span className="sr-only">Open menu</span>
          </button>
        </SheetTrigger>

        <SheetContent side="left" className="flex flex-col p-0 w-64
                                              bg-white dark:bg-slate-900
                                              border-r border-slate-200 dark:border-slate-800">
          {/* Logo */}
          <div className="flex items-center gap-2.5 px-4 py-5 border-b border-slate-200 dark:border-slate-800">
            <SafeImage src={LogoIcon} alt="BDC" width={28} height={28} priority />
            <div>
              <p className="text-sm font-bold text-slate-900 dark:text-slate-50">Think Big</p>
              <p className="text-xs text-blue-600 font-semibold tracking-wide">Speak Data</p>
            </div>
          </div>

          {/* User */}
          <div className="px-3 py-3 border-b border-slate-200 dark:border-slate-800">
            <Link
              href="/myaccount"
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-3 p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <Avatar className="h-8 w-8 flex-shrink-0">
                <AvatarImage src={`https://api.dicebear.com/9.x/adventurer/png?seed=${encodeURIComponent(user?.name || "User")}`} alt={user?.name || "User"} />
                <AvatarFallback className="text-xs bg-blue-50 dark:bg-slate-800 text-blue-600 font-semibold">
                  {user?.name?.charAt(0) || "U"}
                </AvatarFallback>
              </Avatar>
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{user?.name || "Guest"}</p>
                <p className="text-xs text-slate-500">{user?.role?.replace("ROLE_", "") || "Member"}</p>
              </div>
            </Link>
          </div>

          {/* Nav */}
          <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
            {sidebarSections.map((section, i) => (
              <div key={section.title}>
                {i > 0 && <div className="border-t border-slate-200 dark:border-slate-800 mb-3" />}
                <p className="text-xs font-semibold text-slate-400 dark:text-slate-600 uppercase tracking-wider px-3 mb-1.5">
                  {section.title}
                </p>
                <ul className="space-y-0.5">
                  {section.links.map((link) => {
                    const isActive = pathname === link.route;
                    const Icon = link.icon;
                    return (
                      <li key={link.route}>
                        <Link
                          href={link.route}
                          onClick={() => setIsOpen(false)}
                          className={cn(
                            "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors duration-200",
                            isActive
                              ? "bg-blue-600 text-white"
                              : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                          )}
                        >
                          <Icon className="h-4 w-4 flex-shrink-0" />
                          {link.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>

          {/* Footer */}
          <div className="border-t border-slate-200 dark:border-slate-800 p-2 space-y-0.5">
            {isAdmin && (
              <Link
                href="/settings"
                onClick={() => setIsOpen(false)}
                className={cn(
                  "w-full flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors duration-200",
                  pathname.startsWith("/settings")
                    ? "bg-blue-600 text-white"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                )}
              >
                <Settings className="h-4 w-4" />
                Settings
              </Link>
            )}
            <button
              onClick={() => { setTheme(theme === "light" ? "dark" : "light"); setIsOpen(false); }}
              className="w-full flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium
                         text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </button>
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium
                         text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </SheetContent>
      </Sheet>

      {/* Center logo */}
      <div className="flex-1 flex justify-center">
        <Link href="/" className="flex items-center gap-2">
          <SafeImage src={LogoIcon} alt="BDC" width={28} height={28} priority />
        </Link>
      </div>

      {/* Spacer to balance menu button */}
      <div className="w-9" />
    </header>
  );
};

export default MobileNav;