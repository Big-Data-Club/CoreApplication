import {
  LayoutDashboard,
  Users,
  Calendar,
  ClipboardList,
  Trophy,
  Dot,
  Settings,
} from "lucide-react";
import bdclogo from "@/assets/bdclogo.png"

export const sidebarSections = [
  {
    title: "Main Menu",
    links: [
      {
        label: "Dashboard",
        route: "/dashboard",
        icon: LayoutDashboard,
        iconColor: "text-blue-500",
      },
      {
        label: "Users",
        route: "/users",
        icon: Users,
        iconColor: "text-blue-500",
      },
      {
        label: "Events",
        route: "/events",
        icon: Calendar,
        iconColor: "text-blue-500",
      },
      {
        label: "Tasks",
        route: "/tasks",
        icon: ClipboardList,
        iconColor: "text-blue-500",
      },
      {
        label: "Leaderboard",
        route: "/leaderboard",
        icon: Trophy,
        iconColor: "text-blue-500",
      },
      {
        label: "Shared Knowledge",
        route: "/lms",
        icon: Trophy,
        iconColor: "text-blue-500",
      },
    ],
  },
  {
    title: "Competition",
    links: [
      {
        label: "Data Hackathon",
        route: "/hackathon2025",
        icon: Dot,
        iconColor: "text-blue-500",
      },
    ],
  },
  // {
  //   title: "Others",
  //   links: [
  //     {
  //       label: "Settings",
  //       route: "/settings",
  //       icon: Settings,
  //       iconColor: "text-blue-500",
  //     },
  //   ],
  // },
];

// Dùng cho logo
export const LogoIcon = bdclogo;