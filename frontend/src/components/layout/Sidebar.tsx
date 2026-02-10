"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import { sidebarSections, LogoIcon } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ChevronsLeft, ChevronsRight, LogOut, Sun, Moon } from "lucide-react";
import { useUser } from "@/store/UserContext";
import { useTheme } from "next-themes";
import { userService } from "@/services/userService";

const MIN_WIDTH = 80;
const MAX_WIDTH = 320;
const DEFAULT_WIDTH = 256;

const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { user, setUser } = useUser();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [width, setWidth] = useState<number>(DEFAULT_WIDTH);
  const previousWidthRef = useRef<number>(DEFAULT_WIDTH);
  const startResizeRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const toggleSidebar = () => {
    if (!isCollapsed) {
      previousWidthRef.current = width;
      setWidth(MIN_WIDTH);
      setIsCollapsed(true);
    } else {
      const restore = Math.min(Math.max(previousWidthRef.current || DEFAULT_WIDTH, DEFAULT_WIDTH), MAX_WIDTH);
      setWidth(restore);
      setIsCollapsed(false);
    }
  };

  const toggleTheme = () => {
    setTheme(theme === "light" ? "dark" : "light");
  };

  useEffect(() => {
    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!startResizeRef.current) return;
      const clientX = "touches" in e ? e.touches[0].clientX : (e as MouseEvent).clientX;
      const dx = clientX - startResizeRef.current.startX;
      let newWidth = startResizeRef.current.startWidth + dx;
      if (newWidth < MIN_WIDTH) newWidth = MIN_WIDTH;
      if (newWidth > MAX_WIDTH) newWidth = MAX_WIDTH;
      setWidth(newWidth);
      setIsCollapsed(newWidth <= MIN_WIDTH + 1);
    };

    const onUp = () => {
      startResizeRef.current = null;
      previousWidthRef.current = width;
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchend", onUp);

    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchend", onUp);
    };
  }, [width]);

  const onResizeStart = (e: React.MouseEvent | React.TouchEvent) => {
    const clientX = "touches" in e ? (e as React.TouchEvent).touches[0].clientX : (e as React.MouseEvent).clientX;
    startResizeRef.current = { startX: clientX, startWidth: width };
    document.body.style.userSelect = "none";
  };

  const handleLogout = async () => {
    try {
      userService.logout()
      document.cookie = "authToken=; path=/; max-age=0";
      setUser(null);
      router.push("/login");
    } catch (err) {
      console.error("Logout error:", err);
      document.cookie = "authToken=; path=/; max-age=0";
      setUser(null);
      router.push("/login");
    }
  };

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        style={{ width: `${width}px` }}
        className={cn(
          "group relative flex flex-col h-screen transition-all duration-200 ease-in-out z-20",
          "bg-transparent border-r border-gray-100",
          "hidden md:flex"
        )}
      >
        <div className="flex flex-col gap-y-1 py-2 px-2 overflow-y-auto no-scrollbar">
          <div className={cn("flex items-center gap-2 px-2", isCollapsed && "justify-center")}>
            <span className={cn("text-xl font-bold text-gray-800", isCollapsed && "justify-center")}>
              <Image src={LogoIcon} alt="Big Data Club" width={100} height={100} priority />
            </span>

            {/* user display: avoid using client-only avatar src on the server */}
            <span className={cn("text-lg font-bold text-gray-800", isCollapsed && "hidden")}>
              <p className="text-sm leading-tight">Think Big <br/> Speak Data</p>
            </span>
          </div>

          <div className="mt-4 px-2">
            <Link href="/myaccount" className={cn("flex items-center gap-3 p-2 rounded-lg hover:bg-gray-100 transition-colors")}>
              <Avatar className="h-10 w-10 shrink-0">
                {mounted ? (
                  // only add the external avatar image after mount to avoid server/client difference
                  <AvatarImage
                    src={`https://api.dicebear.com/9.x/adventurer/svg?seed=${encodeURIComponent(user?.name || "User")}`}
                    alt="User"
                    className="h-[50px] w-[50px]"
                  />
                ) : (
                  <AvatarFallback>{user?.name?.charAt(0) || "U"}</AvatarFallback>
                )}
              </Avatar>
              <div className={cn(isCollapsed && "hidden")}>
                <p className="font-semibold text-sm text-gray-800">{user?.name || "Guest"}</p>
                <p className="text-xs text-gray-600">{user?.role?.replace("ROLE_", "") || "Member"}</p>
              </div>
            </Link>
          </div>

          <nav className="flex flex-col gap-3 mt-3">
            {sidebarSections.map((section, index) => (
              <div key={section.title} className={cn(index > 0 && "pt-2 border-t border-gray-100")}>
                <h3
                  className={cn(
                    "text-xs font-semibold text-gray-500 uppercase mb-3 px-2",
                    isCollapsed && "text-center mb-2"
                  )}
                >
                  {isCollapsed ? section.title.charAt(0) : section.title}
                </h3>
                <ul className="flex flex-col gap-2 list-none">
                  {section.links.map((link) => {
                    const isActive = pathname === link.route;
                    const LinkIcon = link.icon;

                    return (
                      <li key={link.route}>
                        {isCollapsed ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Link
                                href={link.route}
                                className={cn(
                                  "flex items-center justify-center h-10 w-10 mx-auto rounded-xl transition-all duration-200",
                                  isActive
                                    ? "bg-blue-600 text-white"
                                    : "bg-transparent text-gray-600 hover:bg-gray-100"
                                )}
                              >
                                <LinkIcon
                                  className={cn("h-5 w-5 shrink-0", link.iconColor)}
                                />
                                <span className="sr-only">{link.label}</span>
                              </Link>
                            </TooltipTrigger>
                            <TooltipContent side="right">
                              {link.label}
                            </TooltipContent>
                          </Tooltip>
                        ) : (
                          <Link
                            href={link.route}
                            className={cn(
                              "flex items-center gap-3 rounded-xl px-4 py-2 text-sm font-medium transition-all duration-200",
                              isActive
                                ? "bg-blue-600 text-white"
                                : "bg-transparent text-gray-600 hover:bg-gray-100"
                            )}
                          >
                            <LinkIcon
                              className={cn("h-5 w-5 shrink-0", link.iconColor)}
                            />
                            {link.label}
                          </Link>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        <div className="p-1 border-t border-gray-100 flex flex-col gap-2">
          <Button onClick={toggleTheme} variant="ghost" className="w-full justify-center text-gray-600 hover:text-gray-800 hover:bg-gray-100">
            {isCollapsed ? (
              // collapsed: show icon only; if not mounted render a neutral placeholder (same on server & client)
              mounted ? (theme === "light" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />)
                      : <span className="h-5 w-5 inline-block" aria-hidden />
            ) : (
              <div className="flex items-center gap-2">
                {mounted ? (theme === "light" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />)
                         : <span className="h-5 w-5 inline-block" aria-hidden />}
                <span>{mounted ? (theme === "light" ? "Dark Mode" : "Light Mode") : "Theme"}</span>
              </div>
            )}
            <span className="sr-only">Toggle theme</span>
          </Button>
          <Button
            onClick={handleLogout}
            variant="ghost"
            className="w-full justify-center text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            {isCollapsed ? (
              <LogOut className="h-5 w-5" />
            ) : (
              <div className="flex items-center gap-2">
                <LogOut className="h-5 w-5" />
                <span>Logout</span>
              </div>
            )}
            <span className="sr-only">Logout</span>
          </Button>
          <Button
            onClick={toggleSidebar}
            variant="ghost"
            className="w-full justify-center text-gray-600 hover:text-gray-800 hover:bg-gray-100"
          >
            {isCollapsed ? (
              <ChevronsRight className="h-5 w-5" />
            ) : (
              <div className="flex items-center gap-2">
                <ChevronsLeft className="h-5 w-5" />
                <span>Collapse</span>
              </div>
            )}
            <span className="sr-only">Toggle sidebar</span>
          </Button>
        </div>

        <div
          onMouseDown={onResizeStart}
          onTouchStart={onResizeStart}
          className="absolute top-0 right-0 h-full w-2 -mr-1 cursor-col-resize opacity-0 group-hover:opacity-100 transition-opacity"
          title="Kéo để thay đổi chiều rộng"
          aria-hidden
        />
      </aside>
    </TooltipProvider>
  );
};

export default Sidebar;