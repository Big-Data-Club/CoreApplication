"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import picture from "@/data/picture.png"

export default function TetCountdown() {
  // Target: Tết Nguyên Đán Bính Ngọ 2026 (Ngày 17/02/2026 Dương lịch)
  // Lưu ý: Tháng trong JS bắt đầu từ 0 (Tháng 1 là 0, Tháng 2 là 1)
  const targetDate = new Date(2026, 1, 17, 0, 0, 0).getTime();

  const [timeLeft, setTimeLeft] = useState({
    days: 0,
    hours: 0,
    minutes: 0,
    seconds: 0,
  });

  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date().getTime();
      const distance = targetDate - now;

      if (distance < 0) {
        clearInterval(interval);
      } else {
        setTimeLeft({
          days: Math.floor(distance / (1000 * 60 * 60 * 24)),
          hours: Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)),
          minutes: Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)),
          seconds: Math.floor((distance % (1000 * 60)) / 1000),
        });
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [targetDate]);

  return (
    <div className="relative w-full h-screen overflow-y-auto no-scrollbar bg-[#2a0a0d] flex flex-col items-center justify-center">
      
      {/* 1. Background Effects (Giả lập không gian đỏ thắm của ảnh) */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Gradient nền tối giống góc ảnh */}
        <div className="absolute inset-0 bg-gradient-to-b from-[#1a0506] via-[#3a0e11] to-[#1a0506] opacity-90"></div>
        {/* Hiệu ứng đốm sáng vàng nhẹ (như đèn lồng hắt sáng) */}
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-orange-500/10 rounded-full blur-[100px]"></div>
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-red-600/10 rounded-full blur-[100px]"></div>
      </div>

      <main className="relative z-10 flex flex-col items-center justify-center w-full px-4 text-center">
        
        {/* 2. Hình ảnh trung tâm (Logo BDC style Tết) */}
        {/* Bạn hãy đặt file ảnh vào thư mục public và đổi tên thành tet-bdc.jpg */}
        <div className="relative w-full max-w-2xl aspect-square md:aspect-[4/3] lg:aspect-[16/9] mb-8 animate-fade-in-up">
            <Image
              src={picture}
              alt="Big Data Club Tet Binh Ngo"
              fill
              className="object-contain drop-shadow-2xl"
              priority
            />
        </div>

        {/* 3. Lời chúc (Font Serif sang trọng) */}
        <div className="space-y-4 mb-12 animate-slide-up">
          <h2 className="text-[#e8c26e] text-lg md:text-xl tracking-[0.2em] font-serif uppercase opacity-80">
            Chào Xuân Bính Ngọ 2026
          </h2>
          <h1 className="text-4xl md:text-6xl font-serif font-bold text-transparent bg-clip-text bg-gradient-to-r from-[#bf953f] via-[#fcf6ba] to-[#bf953f] drop-shadow-sm">
            CUNG CHÚC TÂN XUÂN
          </h1>
        </div>

        {/* 4. Bộ đếm ngược (Style tối giản, số vàng kim loại) */}
        <div className="grid grid-cols-4 gap-4 md:gap-8 lg:gap-12 max-w-4xl w-full">
          <TimeUnit value={timeLeft.days} label="Ngày" />
          <TimeUnit value={timeLeft.hours} label="Giờ" />
          <TimeUnit value={timeLeft.minutes} label="Phút" />
          <TimeUnit value={timeLeft.seconds} label="Giây" />
        </div>

        {/* 5. Footer Text */}
        <div className="mt-16 text-[#8a5a5a] text-sm tracking-widest font-serif">
           BIG DATA CLUB - THINK BIG • SPEAK DATA
        </div>
      </main>
    </div>
  );
}

// Component hiển thị từng đơn vị thời gian
function TimeUnit({ value, label }: { value: number; label: string }) {
  // Format số luôn có 2 chữ số (05, 09...)
  const formattedValue = value < 10 ? `0${value}` : value;

  return (
    <div className="flex flex-col items-center group">
      <div className="relative">
        {/* Border vàng mỏng bao quanh số */}
        <div className="w-16 h-16 md:w-24 md:h-24 lg:w-32 lg:h-32 flex items-center justify-center rounded-2xl bg-[#3d1013]/50 border border-[#e8c26e]/30 backdrop-blur-sm shadow-[0_0_15px_rgba(232,194,110,0.1)] group-hover:border-[#e8c26e]/60 transition-colors duration-500">
          <span className="text-3xl md:text-5xl lg:text-6xl font-bold text-[#e8c26e] font-mono tabular-nums">
            {formattedValue}
          </span>
        </div>
      </div>
      <span className="mt-4 text-[#cfb07e] text-xs md:text-sm font-serif uppercase tracking-widest">
        {label}
      </span>
    </div>
  );
}