"use client";
import Image from "next/image";
import React from "react";

export default function Avatar({ code, size = 44 }: { code: string; size?: number }) {
  const src = `https://api.dicebear.com/9.x/adventurer/svg?seed=${encodeURIComponent(code)}`;
  return (
    <Image
      src={src}
      alt={code}
      width={size}
      height={size}
      unoptimized
      className="rounded-full"
      style={{ width: size, height: size }}
    />
  );
}
