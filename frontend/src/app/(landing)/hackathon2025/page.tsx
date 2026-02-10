'use client'

import React, { useState, useEffect } from 'react';
import { Calendar, Trophy, MapPin, Target, Lightbulb, Clock } from 'lucide-react';
import TimelineProgress from './TimelineProgress';

// ============================================
// CONFIGURATION - Cấu hình ngày tháng tập trung
// ============================================
const EVENT_CONFIG = {
  // Vòng 1: Đăng ký
  registrationStart: new Date('2025-10-30'),
  registrationEnd: new Date('2025-11-09T23:59:59'),
  
  // Vòng 2: Thi on-site
  round2Date: new Date('2025-11-22'),
  
  // Vòng 3: Chung kết
  finalsDate: new Date('2025-11-23'),
};

// Timeline events cho ngày thi Vòng 2
const TIMELINE_EVENTS_ROUND2 = [
  { time: '08:00', title: 'Check-in', description: 'Chương trình văn nghệ chào mừng' },
  { time: '08:30', title: 'Lễ khai mạc', description: 'PGS.TS Thoại Nam phát biểu khai mạc' },
  { time: '09:00', title: 'Công bố đề thi', description: 'Phổ biến nội dung cuộc thi và nhận dữ liệu' },
  { time: '09:30', title: 'Bắt đầu làm bài', description: 'Các đội bắt đầu phân tích và xử lý dữ liệu' },
  { time: '12:00', title: 'Nghỉ trưa', description: 'Nghỉ ngơi và ăn trưa (30 phút)' },
  { time: '12:30', title: 'Tiếp tục làm bài', description: 'Phát triển giải pháp và mô hình' },
  { time: '17:00', title: 'Nộp bài', description: 'Kết thúc vòng thi số 2' },
  { time: '17:30', title: 'Bế mạc', description: 'Thông báo kết thúc vòng 2, tổ chức Minigame và văn nghệ bế mạc dành cho thí sinh' },
  { time: '19:00', title: 'Kết quả', description: 'Thông báo kết quả vòng thi số 2 trên Fanpage' },
];

// Timeline events cho ngày thi Vòng 3 (Chung kết)
const TIMELINE_EVENTS_ROUND3 = [
  { time: '08:00', title: 'Check-in', description: 'Đón tiếp các bạn thí sinh và khách mời' },
  { time: '08:15', title: 'Thuyết trình sản phẩm', description: 'Các đội thi trình bày về sản phẩm của mình để chấm điểm' },
  { time: '10:30', title: 'Kết thúc thuyết trình', description: 'Các đội thi nghỉ ngơi chờ kết quả' },
  { time: '11:00', title: 'Công bố kết quả', description: 'Công bố kết quả vòng 3' },
  { time: '11:30', title: 'Bế mạc', description: 'Kết thúc mùa thi BDC Data Hackathon 2025' },
];

export default function BDCHackathonLanding() {
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const getCurrentStatus = () => {
    const now = currentTime;
    const hackathonDate = EVENT_CONFIG.round2Date;
    const finalsDate = EVENT_CONFIG.finalsDate;
    
    if (now.toDateString() === hackathonDate.toDateString()) {
      return { status: 'live', message: 'Vòng 2 đang diễn ra - On-site Competition' };
    } else if (now.toDateString() === finalsDate.toDateString()) {
      return { status: 'finals', message: 'Vòng Chung kết đang diễn ra' };
    } else if (now < hackathonDate) {
      return { status: 'upcoming', message: 'Sắp diễn ra' };
    } else {
      return { status: 'ended', message: 'Đã kết thúc' };
    }
  };

  const formatDate = (date: Date) => {
    return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const status = getCurrentStatus();
  const isRegistrationOpen = currentTime <= EVENT_CONFIG.registrationEnd;

  return (
    <div className="min-h-screen bg-transparent text-black no-scrollbar">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-transparent opacity-30"></div>
        <div className="absolute inset-0 bg-transparent"></div>
        
        <div className="relative container mx-auto px-4 py-16">
          <div className="text-center mb-8">
            <div className="inline-block px-4 py-2 bg-yellow-500 text-black font-bold rounded-full mb-4 animate-pulse">
              {status.message}
            </div>
            <h1 className="text-5xl md:text-7xl font-bold mb-4 bg-clip-text text-transparent bg-gradient-to-r from-blue-700 to-purple-700">
              BDC DATA HACKATHON 2025
            </h1>
            <p className="text-xl md:text-2xl text-gray-700 mb-8">
              Chinh phục thử thách dữ liệu - Tỏa sáng tài năng
            </p>
            <div className="flex justify-center items-center gap-4 text-lg">
              <Clock className="w-6 h-6 text-gray-600" />
              <span className="font-mono text-2xl text-gray-800">
                {currentTime.toLocaleString('vi-VN', { 
                  dateStyle: 'full', 
                  timeStyle: 'medium' 
                })}
              </span>
            </div>
          </div>

          {/* Quick Info Cards */}
          <div className="grid md:grid-cols-3 gap-10 mb-12 justify-items-center mx-auto w-fit">
            <div className="bg-transparent rounded-xl p-2 text-center">
              <Calendar className="w-8 h-8 mb-1 text-blue-600" />
              <h3 className="font-bold text-lg mb-1 text-gray-800">Vòng 2: Thi On-site</h3>
              <p className="text-gray-600">{formatDate(EVENT_CONFIG.round2Date)}</p>
            </div>

            <div className="bg-transparent rounded-xl p-2 text-center">
              <Trophy className="w-8 h-8 mb-1 text-yellow-600" />
              <h3 className="font-bold text-lg mb-1 text-gray-800">Tổng giải thưởng</h3>
              <p className="text-yellow-600">10.000.000 VNĐ</p>
            </div>

            <div className="bg-transparent rounded-xl p-2 text-center">
              <MapPin className="w-8 h-8 mb-1 text-green-600" />
              <h3 className="font-bold text-lg mb-1 text-gray-800">Địa điểm</h3>
              <p className="text-green-600">ĐH Bách Khoa TP.HCM</p>
            </div>
          </div>
        </div>
      </div>

      {/* Timeline & Progress Bar for Round 2 */}
      <TimelineProgress
        events={TIMELINE_EVENTS_ROUND2}
        title="Lịch trình Vòng 2"
        hackathonDate={EVENT_CONFIG.round2Date}
        startHour={8}
        endHour={19}
        endMinute={0}
      />

      {/* Timeline & Progress Bar for Round 3 */}
      <TimelineProgress
        events={TIMELINE_EVENTS_ROUND3}
        title="Lịch trình Vòng 3 - Chung kết"
        hackathonDate={EVENT_CONFIG.finalsDate}
        startHour={8}
        endHour={11}
        endMinute={30}
      />

      {/* Event Details Section */}
      <div className="bg-transparent py-16">
        <div className="container mx-auto px-4">
          <h2 className="text-4xl font-bold text-center mb-12 text-gray-800">Về cuộc thi</h2>
          
          <div className="grid md:grid-cols-2 gap-8 max-w-6xl mx-auto">
            <div className="bg-gray-50 bg-opacity-90 backdrop-blur-lg rounded-xl p-8 border border-gray-200">
              <Target className="w-10 h-10 mb-4 text-blue-600" />
              <h3 className="text-2xl font-bold mb-4 text-gray-800">Mục tiêu cuộc thi</h3>
              <ul className="space-y-3 text-gray-600">
                <li className="flex gap-3"><span className="text-yellow-600">•</span> Tạo sân chơi học thuật lành mạnh cho sinh viên</li>
                <li className="flex gap-3"><span className="text-yellow-600">•</span> Thúc đẩy đổi mới sáng tạo và chuyển đổi số</li>
                <li className="flex gap-3"><span className="text-yellow-600">•</span> Tìm giải pháp thực tiễn cho vấn đề hiện tại</li>
                <li className="flex gap-3"><span className="text-yellow-600">•</span> Phát hiện và ươm mầm tài năng trẻ</li>
              </ul>
            </div>

            <div className="bg-transparent backdrop-blur-lg rounded-xl p-8 border border-gray-200">
              <Lightbulb className="w-10 h-10 mb-4 text-yellow-600" />
              <h3 className="text-2xl font-bold mb-4 text-gray-800">Cấu trúc cuộc thi</h3>
              <div className="space-y-4 text-gray-600">
                <div>
                  <p className="font-bold text-gray-800 mb-1">🎯 Vòng 1: Đăng ký & Sơ loại</p>
                  <p className="text-sm">{formatDate(EVENT_CONFIG.registrationStart)} - {formatDate(EVENT_CONFIG.registrationEnd)} (Online)</p>
                </div>
                <div>
                  <p className="font-bold text-gray-800 mb-1">💻 Vòng 2: Thi trực tiếp</p>
                  <p className="text-sm">{formatDate(EVENT_CONFIG.round2Date)} (On-site tại ĐHBK)</p>
                </div>
                <div>
                  <p className="font-bold text-gray-800 mb-1">🏆 Vòng 3: Chung kết</p>
                  <p className="text-sm">{formatDate(EVENT_CONFIG.finalsDate)} (Thuyết trình tại C5)</p>
                </div>
              </div>
            </div>
          </div>

          {/* Prizes */}
          <div className="mt-12 max-w-4xl mx-auto">
            <div className="bg-gradient-to-r from-yellow-500 to-orange-500 rounded-xl p-8 text-center">
              <Trophy className="w-16 h-16 mx-auto mb-4 text-black" />
              <h3 className="text-3xl font-bold text-black mb-6">Giải thưởng hấp dẫn</h3>
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-black bg-opacity-20 rounded-lg p-6">
                  <p className="text-2xl font-bold mb-2 text-white">🥇 Giải Nhất</p>
                  <p className="text-3xl font-bold text-white">5.000.000 VNĐ</p>
                </div>
                <div className="bg-black bg-opacity-20 rounded-lg p-6">
                  <p className="text-2xl font-bold mb-2 text-white">🥈 Giải Nhì</p>
                  <p className="text-3xl font-bold text-white">3.000.000 VNĐ</p>
                </div>
                <div className="bg-black bg-opacity-20 rounded-lg p-6">
                  <p className="text-2xl font-bold mb-2 text-white">🥉 Giải Ba</p>
                  <p className="text-3xl font-bold text-white">2.000.000 VNĐ</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Contact & Registration */}
      <div className="container mx-auto px-4 py-16">
        <div className="max-w-2xl mx-auto text-center">
          {isRegistrationOpen && (
            <>
              <h2 className="text-4xl font-bold mb-8 text-gray-800">Đăng ký tham gia</h2>
              <p className="text-xl text-gray-600 mb-8">
                Thời gian đăng ký: <span className="font-bold text-yellow-600">
                  {formatDate(EVENT_CONFIG.registrationStart)} - {formatDate(EVENT_CONFIG.registrationEnd)}
                </span>
              </p>
              
              <a 
                href="https://forms.gle/p2JvvW78S5nndvePA" 
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-block bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white font-bold text-xl px-12 py-4 rounded-full transition-all transform hover:scale-105 shadow-lg mb-12"
              >
                ĐĂNG KÝ NGAY
              </a>
            </>
          )}
        </div>
      </div>
    </div>
  );
}