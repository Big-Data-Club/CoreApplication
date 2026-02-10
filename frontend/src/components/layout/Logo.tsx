"use client"

import Image from "next/image";
import { LogoIcon } from "@/lib/constants";

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="w-20 h-20 rounded-lg bg-gradient-to-br from-indigo-500 to-pink-400 flex items-center justify-center shadow-md">
        <Image
          src={LogoIcon}
          alt="Big Data Club"
          width={120}
          height={120}
          priority
        />
      </div>
    </div>
  );
}