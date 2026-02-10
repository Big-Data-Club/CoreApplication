"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { Menu, LogOut, Sun, Moon } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { sidebarSections, LogoIcon } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useState } from "react";
import { useUser } from "@/store/UserContext";
import { useTheme } from "next-themes";
import { userService } from "@/services/userService";

const MobileNav = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { user, setUser } = useUser();
  const { theme, setTheme } = useTheme();
  const [isOpen, setIsOpen] = useState(false);

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
    setIsOpen(false);
  };

  const toggleTheme = () => {
    setTheme(theme === "light" ? "dark" : "light");
    setIsOpen(false);
  };

  return (
    <header className="flex md:hidden items-center h-14 sm:h-16 px-3 sm:px-4 bg-white/95 dark:bg-slate-700/95 sticky top-0 z-50 shadow-sm border-b border-gray-100 dark:border-slate-600">
      <Sheet open={isOpen} onOpenChange={setIsOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-600">
            <Menu className="h-5 w-5 sm:h-6 sm:w-6" />
            <span className="sr-only">Open menu</span>
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="flex flex-col p-0 w-64 bg-white/95 dark:bg-slate-700/95">
          <div className="flex-1 flex flex-col gap-y-4 py-4 px-4 overflow-y-auto">
            <div className="flex items-center gap-3 px-2">
              <span className="text-2xl font-bold text-gray-800 dark:text-gray-100">
                <Image
                  src={LogoIcon}
                  alt="Big Data Club"
                  width={80}
                  height={80}
                  priority
                />
              </span>
              <span className="text-xl font-bold text-gray-800 dark:text-gray-100">
                <p>Think Big <br/> Speak Data</p>
              </span>
            </div>

            <div className="mt-4 px-2">
              <Link
                href="/myaccount"
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-600"
                onClick={() => setIsOpen(false)}
              >
                <Avatar className="h-10 w-10">
                  <AvatarImage src={`https://api.dicebear.com/9.x/adventurer/svg?seed=${user?.name || "User"}`} alt="User" />
                  <AvatarFallback>{user?.name?.charAt(0) || "U"}</AvatarFallback>
                </Avatar>
                <div>
                  <p className="font-semibold text-sm text-gray-800 dark:text-gray-100">{user?.name || "Guest"}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{user?.role.replace("ROLE_", "") || "Member"}</p>
                </div>
              </Link>
            </div>

            <nav className="flex flex-col gap-4 mt-6">
              {sidebarSections.map((section) => (
                <div key={section.title}>
                  <h3 className="text-xs font-semibold text-gray-400 dark:text-gray-400 uppercase mb-2 px-4">
                    {section.title}
                  </h3>
                  <ul className="flex flex-col gap-1">
                    {section.links.map((link) => {
                      const isActive = pathname === link.route;
                      const LinkIcon = link.icon;

                      return (
                        <li key={link.route}>
                          <Link
                            href={link.route}
                            className={cn(
                              "flex items-center gap-3 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                              isActive
                                ? "bg-blue-600 text-white"
                                : "text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-600 hover:text-gray-900 dark:hover:text-gray-100"
                            )}
                            onClick={() => setIsOpen(false)}
                          >
                            <LinkIcon className={cn("h-5 w-5", link.iconColor)} />
                            {link.label}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </nav>
          </div>

          <div className="p-4 border-t border-gray-100 dark:border-slate-600 flex flex-col gap-2">
            <Button
              onClick={toggleTheme}
              variant="ghost"
              className="w-full justify-start text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-slate-600"
            >
              <div className="flex items-center gap-3">
                {theme === "light" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
                <span>{theme === "light" ? "Dark Mode" : "Light Mode"}</span>
              </div>
              <span className="sr-only">Toggle theme</span>
            </Button>
            <Button
              onClick={handleLogout}
              variant="ghost"
              className="w-full justify-start text-red-600 hover:text-red-700 dark:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              <div className="flex items-center gap-3">
                <LogOut className="h-5 w-5" />
                <span>Logout</span>
              </div>
              <span className="sr-only">Logout</span>
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex-1 flex justify-center">
        <Link href="/" className="flex items-center gap-2">
          <span className="font-semibold">
            <Image
              src={LogoIcon}
              alt="Big Data Club"
              width={40}
              height={40}
              priority
            />
          </span>
        </Link>
      </div>
    </header>
  );
};

export default MobileNav;