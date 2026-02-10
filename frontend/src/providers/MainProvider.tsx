"use client";

import { SessionProvider } from "next-auth/react";
import { ThemeProvider } from "next-themes";
import { Toaster } from "react-hot-toast";
import { ReactNode } from "react";
import { UserProvider } from "@/store/UserContext";

export default function Providers({ children }: { children: ReactNode }) {
  return (
    <UserProvider>
      <SessionProvider>
        <ThemeProvider attribute="class"
          defaultTheme="light"
          enableSystem={true}
          enableColorScheme={true} 
          storageKey="bdc-theme" 
          >
          {children}
          <Toaster />
        </ThemeProvider>
      </SessionProvider>
    </UserProvider>
  );
}