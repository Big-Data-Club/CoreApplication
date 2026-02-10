'use client'

import React, { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';

interface TimelineEvent {
  time: string;
  title: string;
  description: string;
}

interface TimelineProgressProps {
  events: TimelineEvent[];
  title: string;
  hackathonDate: Date;
  startHour?: number;
  endHour?: number;
  endMinute?: number;
}

export default function TimelineProgress({
  events,
  title,
  hackathonDate,
  startHour = 8,
  endHour = 16,
  endMinute = 30,
}: TimelineProgressProps) {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [activePhase, setActivePhase] = useState<number | null>(null);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const now = currentTime;
    
    if (now.toDateString() === hackathonDate.toDateString()) {
      const currentHour = now.getHours();
      const currentMinute = now.getMinutes();
      const currentTimeInMinutes = currentHour * 60 + currentMinute;

      for (let i = 0; i < events.length; i++) {
        const [hour, minute] = events[i].time.split(':').map(Number);
        const eventTimeInMinutes = hour * 60 + minute;
        
        const nextEventTime = i < events.length - 1 
          ? events[i + 1].time.split(':').map(Number)
          : [23, 59];
        const nextEventTimeInMinutes = nextEventTime[0] * 60 + nextEventTime[1];

        if (currentTimeInMinutes >= eventTimeInMinutes && currentTimeInMinutes < nextEventTimeInMinutes) {
          setActivePhase(i);
          break;
        }
      }
    }
  }, [currentTime, hackathonDate, events]);

  const getCountdown = (targetTime: string) => {
    const now = currentTime;
    const [hour, minute] = targetTime.split(':').map(Number);
    const target = new Date(hackathonDate);
    target.setHours(hour, minute, 0, 0);

    const diff = target.getTime() - now.getTime();
    
    if (diff < 0) return 'Đã hoàn thành';

    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };

  const getOverallProgress = () => {
    const now = currentTime;
    
    const startTime = new Date(hackathonDate);
    startTime.setHours(startHour, 0, 0, 0);
    
    const endTime = new Date(hackathonDate);
    endTime.setHours(endHour, endMinute, 0, 0);

    // Nếu qua ngày của sự kiện (ngày hôm sau hoặc sau), hiển thị 100%
    if (now > endTime) return 100;
    
    // Nếu chưa tới ngày của sự kiện, hiển thị 0%
    if (now.toDateString() !== hackathonDate.toDateString()) {
      return 0;
    }

    // Nếu hôm nay nhưng trước giờ bắt đầu
    if (now < startTime) return 0;

    const totalDuration = endTime.getTime() - startTime.getTime();
    const elapsed = now.getTime() - startTime.getTime();
    
    return Math.min(100, Math.max(0, (elapsed / totalDuration) * 100));
  };

  const calculatePosition = (time: string) => {
    const [hour, min] = time.split(':').map(Number);
    const eventMinutes = (hour - startHour) * 60 + min;
    const totalMinutes = (endHour - startHour) * 60 + endMinute;
    return (eventMinutes / totalMinutes) * 100;
  };

  const getNearestEvents = () => {
    const now = currentTime;
    const overallProgress = getOverallProgress();
    
    // Nếu cuộc thi đã kết thúc (100%), hiển thị tất cả sự kiện
    if (overallProgress === 100) {
      return events.map((_, index) => index);
    }
    
    // Nếu chưa đến ngày của sự kiện, hiển thị sự kiện đầu tiên
    if (now.toDateString() !== hackathonDate.toDateString()) {
      return [0];
    }

    const currentHour = now.getHours();
    const currentMinute = now.getMinutes();
    const currentTimeInMinutes = currentHour * 60 + currentMinute;

    let pastEventIndex = -1;
    let upcomingEventIndex = -1;

    for (let i = 0; i < events.length; i++) {
      const [hour, minute] = events[i].time.split(':').map(Number);
      const eventTimeInMinutes = hour * 60 + minute;

      if (eventTimeInMinutes <= currentTimeInMinutes) {
        pastEventIndex = i;
      } else if (upcomingEventIndex === -1) {
        upcomingEventIndex = i;
      }
    }

    const nearestEvents:number[] = [];
    if (pastEventIndex >= 0) {
      nearestEvents.push(pastEventIndex);
    }
    if (upcomingEventIndex >= 0) {
      nearestEvents.push(upcomingEventIndex);
    }

    return nearestEvents;
  };

  const formatDate = (date: Date) => {
    return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const overallProgress = getOverallProgress();
  const nearestEvents = getNearestEvents();

  return (
    <div className="container mx-auto px-4 py-5">
      <h2 className="text-4xl font-bold text-center mb-12 text-gray-800">
        <Clock className="inline w-10 h-10 mr-3 text-gray-600" />
        {title} - {formatDate(hackathonDate)}
      </h2>
      
      {/* Enhanced Progress Bar with Checkpoints */}
      <div className="max-w-7xl mx-auto mb-12">
        <div className="bg-transparent backdrop-blur-lg rounded-2xl p-8 border-2 border-gray-200 shadow-xl">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-2xl font-bold text-gray-800">Tiến độ cuộc thi</h3>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-600">Hoàn thành:</span>
              <span className="text-3xl font-mono font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                {overallProgress.toFixed(1)}%
              </span>
            </div>
          </div>
          
          {/* Progress Bar Container with more space */}
          <div className="relative py-56">
            {/* Main Progress Track - centered vertically */}
            <div className="absolute top-1/2 left-0 right-0 -translate-y-1/2">
              <div className="relative h-3 bg-gray-300 rounded-full overflow-hidden shadow-inner">
                <div 
                  className="absolute top-0 left-0 h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 transition-all duration-1000 ease-out rounded-full shadow-lg"
                  style={{ width: `${overallProgress}%` }}
                >
                  <div className="absolute inset-0 bg-white opacity-30 animate-pulse"></div>
                  <div className="absolute right-0 top-1/2 -translate-y-1/2 w-4 h-4 bg-white rounded-full shadow-lg animate-pulse"></div>
                </div>
              </div>
            </div>
            
            {/* Checkpoints */}
            <div className="absolute top-1/2 left-0 right-0 -translate-y-1/2">
              {events.map((event, index) => {
                const isVisible = nearestEvents.includes(index);
                
                if (!isVisible) {
                  return null;
                }

                const position = calculatePosition(event.time);
                const countdown = getCountdown(event.time);
                const isPassed = countdown === 'Đã hoàn thành';
                const isActive = activePhase === index;
                
                // Xếp các card theo 2 hàng: chẵn ở trên, lẻ ở dưới
                const isTopRow = index % 2 === 0;
                
                return (
                  <div 
                    key={index} 
                    className="absolute top-0 left-0"
                    style={{ left: `${position}%` }}
                  >
                    {/* Container chứa toàn bộ: Card -> Line -> Dot, căn giữa theo dot */}
                    <div className="absolute left-0 top-0 -translate-x-1/2 flex flex-col items-center">
                      
                      {/* Card ở trên (nếu isTopRow = true) */}
                      {isTopRow && (
                        <>
                          {/* Event Info Card */}
                          <div className={`
                            p-4 rounded-xl text-center min-w-[140px] max-w-[180px] mb-2 -translate-y-60
                            transition-all duration-300 transform
                            ${isActive 
                              ? 'bg-yellow-50 border-2 border-yellow-400 scale-105 shadow-xl z-30' 
                              : isPassed
                                ? 'bg-green-50 border-2 border-green-300 shadow-md z-10'
                                : 'bg-white border-2 border-gray-300 shadow-md z-10'
                            }
                          `}>
                            {/* Time */}
                            <div className={`
                              text-xl font-bold mb-1
                              ${isActive ? 'text-yellow-600' : isPassed ? 'text-green-600' : 'text-gray-700'}
                            `}>
                              {event.time}
                            </div>
                            
                            {/* Title */}
                            <div className={`
                              text-sm font-semibold mb-2
                              ${isActive ? 'text-yellow-800' : isPassed ? 'text-green-700' : 'text-gray-600'}
                            `}>
                              {event.title}
                            </div>
                            
                            {/* Description */}
                            <div className="text-xs text-gray-500 mb-2">
                              {event.description}
                            </div>
                            
                            {/* Countdown or Status */}
                            {!isPassed && (
                              <div className={`
                                text-lg font-mono font-bold mt-2 pt-2 border-t
                                ${isActive 
                                  ? 'text-yellow-600 border-yellow-300 animate-pulse' 
                                  : 'text-gray-600 border-gray-300'
                                }
                              `}>
                                {countdown}
                              </div>
                            )}
                            
                            {isPassed && (
                              <div className="flex items-center justify-center gap-1 mt-2 pt-2 border-t border-green-300 text-green-600 font-semibold text-xs">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                                <span>Hoàn thành</span>
                              </div>
                            )}
                          </div>
                          
                          {/* Connector Line */}
                          <div className={`
                            w-0.5 h-8 -translate-y-60
                            ${isPassed ? 'bg-green-400' : isActive ? 'bg-yellow-400' : 'bg-gray-400'}
                          `}></div>
                        </>
                      )}
                      
                      {/* Checkpoint Dot - luôn ở giữa */}
                      <div className={`
                        w-8 h-8 rounded-full flex items-center justify-center
                        transition-all duration-300 transform 
                        ${isPassed 
                          ? 'bg-green-500 scale-100 shadow-lg shadow-green-500/50' 
                          : isActive 
                            ? 'bg-yellow-400 scale-125 animate-pulse shadow-lg shadow-yellow-400/50 ring-4 ring-yellow-200' 
                            : 'bg-gray-400 scale-90 shadow-md'
                        }
                        border-4 border-white z-20 relative
                        ${isTopRow ? 'mt-0 mb-auto -translate-y-60' : 'mt-auto mb-0'}
                      `}>
                        {isPassed ? (
                          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : isActive ? (
                          <div className="w-3 h-3 bg-white rounded-full animate-ping"></div>
                        ) : (
                          <div className="w-3 h-3 bg-white rounded-full"></div>
                        )}
                      </div>
                      
                      {/* Card ở dưới (nếu isTopRow = false) */}
                      {!isTopRow && (
                        <>
                          {/* Connector Line */}
                          <div className={`
                            w-0.5 h-8
                            ${isPassed ? 'bg-green-400' : isActive ? 'bg-yellow-400' : 'bg-gray-400'}
                          `}></div>
                          
                          {/* Event Info Card */}
                          <div className={`
                            p-4 rounded-xl text-center min-w-[140px] max-w-[180px] mt-2
                            transition-all duration-300 transform
                            ${isActive 
                              ? 'bg-yellow-50 border-2 border-yellow-400 scale-105 shadow-xl z-30' 
                              : isPassed
                                ? 'bg-green-50 border-2 border-green-300 shadow-md z-10'
                                : 'bg-white border-2 border-gray-300 shadow-md z-10'
                            }
                          `}>
                            {/* Time */}
                            <div className={`
                              text-xl font-bold mb-1
                              ${isActive ? 'text-yellow-600' : isPassed ? 'text-green-600' : 'text-gray-700'}
                            `}>
                              {event.time}
                            </div>
                            
                            {/* Title */}
                            <div className={`
                              text-sm font-semibold mb-2
                              ${isActive ? 'text-yellow-800' : isPassed ? 'text-green-700' : 'text-gray-600'}
                            `}>
                              {event.title}
                            </div>
                            
                            {/* Description */}
                            <div className="text-xs text-gray-500 mb-2">
                              {event.description}
                            </div>
                            
                            {/* Countdown or Status */}
                            {!isPassed && (
                              <div className={`
                                text-lg font-mono font-bold mt-2 pt-2 border-t
                                ${isActive 
                                  ? 'text-yellow-600 border-yellow-300 animate-pulse' 
                                  : 'text-gray-600 border-gray-300'
                                }
                              `}>
                                {countdown}
                              </div>
                            )}
                            
                            {isPassed && (
                              <div className="flex items-center justify-center gap-1 mt-2 pt-2 border-t border-green-300 text-green-600 font-semibold text-xs">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                                <span>Hoàn thành</span>
                              </div>
                            )}
                          </div>
                        </>
                      )}
                      
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          
          {/* Status Message */}
          <div className="mt-6 text-center">
            <div className={`
              inline-block px-6 py-3 rounded-full font-semibold text-lg
              ${overallProgress === 0 
                ? 'bg-gray-200 text-gray-700' 
                : overallProgress === 100 
                  ? 'bg-green-100 text-green-700 border-2 border-green-300' 
                  : 'bg-yellow-100 text-yellow-700 border-2 border-yellow-300 animate-pulse'
              }
            `}>
              {overallProgress === 0 && "⏳ Cuộc thi chưa bắt đầu"}
              {overallProgress > 0 && overallProgress < 100 && "🔥 Đang diễn ra"}
              {overallProgress === 100 && "✅ Đã hoàn thành"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}