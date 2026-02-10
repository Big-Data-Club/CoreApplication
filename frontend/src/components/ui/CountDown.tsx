import React from "react";


export default function Countdown({ startTime, endTime }: { startTime?: string; endTime?: string }) {
    if (!startTime || !endTime) return null;
    const now = new Date();
    const start = new Date(startTime);
    const end = new Date(endTime);
    const format = (ms: number) => {
        const days = Math.floor(ms / (1000 * 60 * 60 * 24));
        const hours = Math.floor((ms % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
        return `${days} ngày ${hours} giờ ${minutes} phút`;
    };
    if (now < start) return <span>Bắt đầu sau {format(start.getTime() - now.getTime())}</span>;
    if (now < end) return <span>Kết thúc sau {format(end.getTime() - now.getTime())}</span>;
    return null;
}