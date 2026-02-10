"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { Logo } from "@/components/layout/Logo";
import clubData from "@/data/clubData.json";
import { userService } from "@/services/userService";
import { Button } from "@/components/ui/button";
import { LogOut } from "lucide-react";

export default function LandingPage() {
  const router = useRouter();
  const [hasToken, setHasToken] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const token = document.cookie
      .split("; ")
      .find((row) => row.startsWith("authToken="))
      ?.split("=")[1];
    setHasToken(!!token);

    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleLogout = async () => {
      try {
        userService.logout()
        document.cookie = "authToken=; path=/; max-age=0";
        router.push("/login");
      } catch (err) {
        console.error("Logout error:", err);
        document.cookie = "authToken=; path=/; max-age=0";
        router.push("/login");
      }
  };

  // Intersection Observer Hook for scroll animations
  const useScrollAnimation = (threshold = 0.1) => {
    const [isVisible, setIsVisible] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            setIsVisible(true);
          }
        },
        { threshold }
      );

      if (ref.current) {
        observer.observe(ref.current);
      }

      return () => {
        if (ref.current) {
          observer.unobserve(ref.current);
        }
      };
    }, [threshold]);

    return [ref, isVisible] as const;
  };

  const teamColors = {
    Council: { 
      gradient: "from-amber-500/20 to-orange-500/20",
      border: "border-amber-500/40",
      glow: "shadow-amber-500/20",
      text: "text-amber-600",
      accentGradient: "from-amber-400 to-orange-500"
    },
    Engineer: { 
      gradient: "from-blue-500/20 to-cyan-500/20",
      border: "border-blue-500/40",
      glow: "shadow-blue-500/20",
      text: "text-blue-600",
      accentGradient: "from-blue-400 to-cyan-500"
    },
    Research: { 
      gradient: "from-purple-500/20 to-pink-500/20",
      border: "border-purple-500/40",
      glow: "shadow-purple-500/20",
      text: "text-purple-600",
      accentGradient: "from-purple-400 to-pink-500"
    },
    Event: { 
      gradient: "from-green-500/20 to-emerald-500/20",
      border: "border-green-500/40",
      glow: "shadow-green-500/20",
      text: "text-green-600",
      accentGradient: "from-green-400 to-emerald-500"
    },
    Media: { 
      gradient: "from-pink-500/20 to-rose-500/20",
      border: "border-pink-500/40",
      glow: "shadow-pink-500/20",
      text: "text-pink-600",
      accentGradient: "from-pink-400 to-rose-500"
    }
  };

  const [aboutRef, aboutVisible] = useScrollAnimation();
  const [valuesRef, valuesVisible] = useScrollAnimation();
  const [activitiesRef, activitiesVisible] = useScrollAnimation();
  const [membersRef, membersVisible] = useScrollAnimation();
  const [publicationsRef, publicationsVisible] = useScrollAnimation();
  const [projectsRef, projectsVisible] = useScrollAnimation();
  const [visionRef, visionVisible] = useScrollAnimation();

  return (
    <div className="w-full min-h-screen">
      {/* Navigation Bar - Glassmorphism */}
      <nav 
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
          scrolled 
            ? 'bg-white/15 backdrop-blur-2xl shadow-lg border-b border-white/30' 
            : 'bg-transparent'
        }`}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-20">
            {/* Logo & Brand */}
            <div className="flex items-center gap-3 group cursor-pointer">
              <div className="transform transition-transform duration-300 group-hover:scale-110 group-hover:rotate-3">
                <Logo />
              </div>
              <div>
                <h2 className="text-xl lg:text-2xl font-bold text-[#2c2416] drop-shadow-sm">
                  Big Data Club
                </h2>
                <p className="text-xs lg:text-sm text-[#5a4a3a] font-medium">
                  Think Big • Speak Data
                </p>
              </div>
            </div>

            {/* Navigation Links */}
            <div className="hidden md:flex items-center gap-8">
              {[
                { href: "#about", label: "Về CLB" },
                { href: "#activities", label: "Hoạt Động" },
                { href: "#members", label: "Thành Viên" },
                { href: "#projects", label: "Dự Án" }
              ].map((item, index) => (
                <a 
                  key={index}
                  href={item.href} 
                  className="text-[#2c2416] hover:text-[#5a4a3a] font-medium transition-all duration-300 relative group"
                >
                  {item.label}
                  <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-gradient-to-r from-[#2c2416] to-[#5a4a3a] transition-all duration-300 group-hover:w-full"></span>
                </a>
              ))}
            </div>

            {/* Login button */}
            {hasToken ? (
            <Button
              onClick={handleLogout}
              variant="ghost"
            >
              <div className="flex items-center gap-3">
                <LogOut className="h-5 w-5" />
                <span>Logout</span>
              </div>
              <span className="sr-only">Logout</span>
            </Button>) : (
            <button
              onClick={() => router.push("/login")}
              className="px-6 py-2.5 bg-gradient-to-r from-[#2c2416] to-[#3d3420] text-white font-semibold rounded-xl 
                       hover:shadow-2xl hover:scale-105 transition-all duration-300 
                       border border-white/20 backdrop-blur-sm relative overflow-hidden group"
            >
              <span className="relative z-10">Đăng nhập</span>
              <div className="absolute inset-0 bg-gradient-to-r from-[#3d3420] to-[#2c2416] opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
            </button>
            )}
          </div>
        </div>
      </nav>

      <main className="pt-20">
        {/* Hero Section with Parallax */}
        <section className="min-h-screen flex items-center justify-center px-4 sm:px-6 lg:px-8 relative overflow-hidden">
          {/* Decorative Elements */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <div className="absolute top-20 left-10 w-72 h-72 bg-gradient-to-br from-amber-500/10 to-orange-500/10 rounded-full blur-3xl animate-float"></div>
            <div className="absolute bottom-20 right-10 w-96 h-96 bg-gradient-to-br from-blue-500/10 to-cyan-500/10 rounded-full blur-3xl animate-float-delayed"></div>
            <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-gradient-to-br from-purple-500/10 to-pink-500/10 rounded-full blur-3xl animate-pulse-slow"></div>
          </div>

          <div className="max-w-5xl mx-auto text-center space-y-8 py-20 relative z-10">
            {/* Animated Title */}
            <div className="space-y-4 animate-slide-up">
              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold text-[#2c2416] tracking-tight">
                Welcome to
                <span className="block mt-2 bg-gradient-to-r from-[#2c2416] via-[#5a4a3a] to-[#2c2416] bg-clip-text text-transparent animate-gradient-x">
                  Big Data Club
                </span>
              </h1>
              <p className="text-xl lg:text-2xl text-[#5a4a3a] max-w-3xl mx-auto font-medium animate-fade-in-delayed">
                Khám phá thế giới dữ liệu và phân tích cùng câu lạc bộ hàng đầu của HCMUT
              </p>
            </div>

            {/* CTA buttons */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center pt-8 animate-fade-in-delayed-2">
              {hasToken ? (
                <button
                  onClick={() => router.push("/dashboard")}
                  className="group px-8 py-4 bg-white/20 backdrop-blur-md text-[#2c2416] font-bold rounded-2xl 
                           border-2 border-[#2c2416]/30 hover:border-[#2c2416] hover:shadow-2xl 
                           transform hover:scale-105 transition-all duration-300"
                >
                  <span className="flex items-center gap-2">
                    Go to Management Board
                    <svg className="w-5 h-5 transform group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </span>
                </button>
              ) : (
                <div
                  className="px-8 py-4 bg-white/10 backdrop-blur-md text-[#5a4a3a] font-bold rounded-2xl 
                           border-2 border-[#5a4a3a]/30 cursor-not-allowed opacity-60"
                  title="Phải đăng nhập để đi tới"
                >
                  Go to Management Board
                </div>
              )}
              
              <a 
                href="#about"
                className="group px-8 py-4 bg-gradient-to-r from-[#2c2416] to-[#3d3420] text-white font-bold rounded-2xl 
                         hover:shadow-2xl transform hover:scale-105 transition-all duration-300 relative overflow-hidden"
              >
                <span className="relative z-10 flex items-center gap-2">
                  Tìm Hiểu Thêm
                  <svg className="w-5 h-5 transform group-hover:translate-y-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                  </svg>
                </span>
                <div className="absolute inset-0 bg-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
              </a>
            </div>

            {/* Stats Cards with Stagger Animation */}
            <div className="grid grid-cols-2 md:grid-cols-2 gap-6 pt-16">
              {[
                { value: "200+", label: "Thành Viên và Cựu Thành Viên"},
                { value: "4", label: "Năm Hoạt Động"}
              ].map((stat, index) => (
                <div 
                  key={index}
                  className="p-8 bg-transparent hover:backdrop-blur-md rounded-3xl 
                           hover:bg-white/10 hover:shadow-2xl transform hover:scale-105 transition-all duration-300
                           animate-fade-in-up"
                  style={{ animationDelay: `${index * 150}ms` }}
                >
                  <div className="text-4xl lg:text-5xl font-bold text-[#2c2416] mb-2">
                    {stat.value}
                  </div>
                  <div className="text-sm text-[#5a4a3a] font-medium">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Scroll Indicator */}
          <div className="absolute bottom-10 left-1/2 transform -translate-x-1/2 animate-bounce">
            <div className="w-6 h-10 border-2 border-[#2c2416]/30 rounded-full flex items-start justify-center p-2">
              <div className="w-1 h-3 bg-[#2c2416]/50 rounded-full animate-scroll"></div>
            </div>
          </div>
        </section>

        {/* About Section */}
        <section 
          id="about" 
          ref={aboutRef}
          className={`py-20 px-4 sm:px-6 lg:px-8 transition-all duration-1000 ${
            aboutVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
          }`}
        >
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-4xl lg:text-5xl font-bold text-[#2c2416] mb-4">
                Về Big Data Club
              </h2>
              <div className="w-24 h-1 bg-gradient-to-r from-transparent via-[#2c2416] to-transparent mx-auto"></div>
            </div>

            <div className="grid md:grid-cols-2 gap-8 mb-12">
              {[
                "Big Data Club là câu lạc bộ hàng đầu tại ĐH Bách Khoa TP.HCM, chuyên về lĩnh vực Big Data, Data Science và Artificial Intelligence. Được thành lập vào ngày 23/10/2021 bởi thầy Hoàng Lê Hải Thanh và anh Mai Hoàng Danh, dưới sự hướng dẫn của PGS.TS Thoại Nam cùng các thầy cô trong HPC Lab.",
                "Với phương châm Learning by Doing và tinh thần Think Big - Speak Data, chúng tôi cam kết xây dựng một cộng đồng học tập năng động, nơi mỗi thành viên có thể phát triển kỹ năng, chia sẻ kinh nghiệm và cùng nhau khám phá những điều mới trong thế giới dữ liệu."
              ].map((text, index) => (
                <div 
                  key={index}
                  className={`p-8 bg-white/10 backdrop-blur-md rounded-3xl border border-white/20 
                           hover:shadow-2xl transform hover:scale-[1.02] transition-all duration-500
                           ${aboutVisible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-10'}`}
                  style={{ transitionDelay: `${index * 200}ms` }}
                >
                  <p className="text-[#5a4a3a] leading-relaxed text-lg">
                    {text.split('Learning by Doing').map((part, i) => 
                      i === 0 ? part : (
                        <React.Fragment key={i}>
                          <span className="font-bold text-[#2c2416]">Learning by Doing</span>
                          {part.split('Think Big - Speak Data').map((subpart, j) =>
                            j === 0 ? subpart : (
                              <React.Fragment key={j}>
                                <span className="font-bold text-[#2c2416]">Think Big - Speak Data</span>
                                {subpart}
                              </React.Fragment>
                            )
                          )}
                        </React.Fragment>
                      )
                    )}
                  </p>
                </div>
              ))}
            </div>

            {/* Core Values with Stagger Animation */}
            <div 
              ref={valuesRef}
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
            >
              {[
                { icon: "🎓", title: "Học Hỏi Không Ngừng", desc: "Tinh thần học hỏi và sáng tạo. Trân trọng điểm mạnh của từng cá nhân." },
                { icon: "💡", title: "Dám Nghĩ Dám Làm", desc: "Tư duy đổi mới, không ngại thử nghiệm và thất bại." },
                { icon: "🤝", title: "Chia Sẻ Cởi Mở", desc: "Open Learning - Open Sharing. Lan tỏa tri thức." },
                { icon: "🚀", title: "Học Qua Dự Án", desc: "Learning by Doing - Học từ các dự án thực tế." }
              ].map((value, index) => (
                <div 
                  key={index}
                  className={`group p-6 bg-white/5 backdrop-blur-md rounded-2xl border border-white/20 
                           hover:bg-white/15 hover:shadow-xl hover:border-white/40 
                           transform hover:scale-105 transition-all duration-500
                           ${valuesVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}
                  style={{ transitionDelay: `${index * 100}ms` }}
                >
                  <div className="text-5xl mb-4 transform group-hover:scale-110 group-hover:rotate-12 transition-all duration-300">
                    {value.icon}
                  </div>
                  <h3 className="text-lg font-bold text-[#2c2416] mb-2">
                    {value.title}
                  </h3>
                  <p className="text-sm text-[#5a4a3a]">
                    {value.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Activities Section */}
        <section 
          id="activities" 
          ref={activitiesRef}
          className={`py-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-transparent to-white/5 transition-all duration-1000 ${
            activitiesVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
          }`}
        >
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-4xl lg:text-5xl font-bold text-[#2c2416] mb-4">
                Hoạt Động Của Câu Lạc Bộ
              </h2>
              <div className="w-24 h-1 bg-gradient-to-r from-transparent via-[#2c2416] to-transparent mx-auto"></div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {clubData.activities.map((activity, index) => (
                <div
                  key={activity.id}
                  className={`group bg-white/10 backdrop-blur-md rounded-3xl border border-white/20 overflow-hidden
                           hover:shadow-2xl hover:bg-white/15 transform hover:scale-105 hover:-rotate-1 
                           transition-all duration-500
                           ${activitiesVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}
                  style={{ transitionDelay: `${index * 100}ms` }}
                >
                  {/* Image Container */}
                  <div className="relative h-56 bg-gradient-to-br from-[#d4caba]/30 to-[#5a4a3a]/30 overflow-hidden">
                    <Image
                      src={activity.imageUrl}
                      alt={activity.title}
                      fill
                      className="object-cover transform group-hover:scale-110 group-hover:rotate-2 transition-transform duration-700"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                        if (e.currentTarget.parentElement) {
                          e.currentTarget.parentElement.innerHTML = `
                            <div class="w-full h-full flex items-center justify-center">
                              <span class="text-6xl">📸</span>
                            </div>
                          `;
                        }
                      }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent"></div>
                    
                    {/* Floating Badge */}
                    <div className="absolute top-4 right-4 px-3 py-1 bg-white/90 backdrop-blur-sm rounded-full 
                                  text-xs font-bold text-[#2c2416] shadow-lg">
                      {activity.type}
                    </div>
                  </div>

                  {/* Content */}
                  <div className="p-6">
                    <div className="flex items-center gap-2 text-xs text-[#5a4a3a] mb-3 font-medium">
                      <span className="px-3 py-1 bg-white/20 rounded-full backdrop-blur-sm">
                        {activity.frequency}
                      </span>
                    </div>
                    <h3 className="text-xl font-bold text-[#2c2416] mb-3 group-hover:text-[#3d3420] transition-colors">
                      {activity.title}
                    </h3>
                    <p className="text-sm text-[#5a4a3a] leading-relaxed">
                      {activity.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Members Section */}
        <section 
          id="members" 
          ref={membersRef}
          className={`py-20 px-4 sm:px-6 lg:px-8 transition-all duration-1000 ${
            membersVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
          }`}
        >
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-4xl lg:text-5xl font-bold text-[#2c2416] mb-4">
                Các Thành Viên Hiện Tại
              </h2>
              <p className="text-xl text-[#5a4a3a] italic">
                Big Data Club Members
              </p>
              <div className="w-24 h-1 bg-gradient-to-r from-transparent via-[#2c2416] to-transparent mx-auto mt-4"></div>
            </div>

            {/* Teams */}
            {['council', 'media', 'event', 'engineer', 'research'].map((teamKey, teamIndex) => {
              const teamData = clubData.members[teamKey as keyof typeof clubData.members];
              if (!teamData || teamData.length === 0) return null;
              
              const teamName = teamKey.charAt(0).toUpperCase() + teamKey.slice(1);
              const colors = teamColors[teamName as keyof typeof teamColors];
              
              return (
                <div 
                  key={teamKey} 
                  className={`mb-16 transition-all duration-1000 ${
                    membersVisible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-10'
                  }`}
                  style={{ transitionDelay: `${teamIndex * 150}ms` }}
                >
                  {/* Team Header with Gradient Accent */}
                  <div className="flex items-center gap-4 mb-8 group">
                    <div className={`w-2 h-16 rounded-full bg-gradient-to-b ${colors.accentGradient} ${colors.glow} shadow-xl 
                                  transform group-hover:scale-110 transition-transform duration-300`}></div>
                    <div>
                      <h3 className="text-3xl font-bold text-[#2c2416] group-hover:text-[#3d3420] transition-colors">
                        {teamName} Team
                      </h3>
                      <p className="text-sm text-[#5a4a3a]">{teamData.length} members</p>
                    </div>
                  </div>

                  {/* Team Members Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
                    {teamData.map((member: { id: string; name: string; desc: string; imageUrl: string }, memberIndex: number) => (
                      <div
                        key={member.id}
                        className={`group bg-white/5 backdrop-blur-md rounded-2xl overflow-hidden 
                                 border-2 ${colors.border} hover:shadow-2xl ${colors.glow}
                                 transform hover:scale-110 hover:-translate-y-3 transition-all duration-500
                                 ${membersVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}
                        style={{ transitionDelay: `${teamIndex * 150 + memberIndex * 50}ms` }}
                      >
                        {/* Avatar with Gradient Overlay */}
                        <div className={`relative w-full aspect-square bg-gradient-to-br ${colors.gradient} overflow-hidden`}>
                          <Image
                            src={member.imageUrl}
                            alt={member.name}
                            fill
                            className="object-cover transform group-hover:scale-125 group-hover:rotate-3 transition-all duration-700"
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                              if (e.currentTarget.parentElement) {
                                e.currentTarget.parentElement.innerHTML = `
                                  <div class="w-full h-full flex items-center justify-center">
                                    <span class="text-5xl ${colors.text}">👤</span>
                                  </div>
                                `;
                              }
                            }}
                          />
                          <div className={`absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent 
                                        opacity-0 group-hover:opacity-100 transition-opacity duration-500`}></div>
                        </div>

                        {/* Info */}
                        <div className="p-4 text-center bg-gradient-to-b from-transparent to-white/5">
                          <h4 className="text-sm font-bold text-[#2c2416] mb-1 truncate group-hover:text-[#3d3420] transition-colors">
                            {member.name}
                          </h4>
                          <p className={`text-xs ${colors.text} font-medium`}>
                            {member.desc}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Publications Section */}
        <section 
          ref={publicationsRef}
          className={`py-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-white/5 to-transparent transition-all duration-1000 ${
            publicationsVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
          }`}
        >
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-4xl lg:text-5xl font-bold text-[#2c2416] mb-4">
                Công Bố Khoa Học
              </h2>
              <div className="w-24 h-1 bg-gradient-to-r from-transparent via-[#2c2416] to-transparent mx-auto"></div>
            </div>

            <div className="space-y-6">
              {clubData.publications.map((pub, index) => (
                <div 
                  key={pub.id}
                  className={`group p-6 bg-white/10 backdrop-blur-md rounded-2xl border-l-4 border-[#2c2416]
                           hover:bg-white/15 hover:shadow-2xl hover:border-l-8 
                           transform hover:translate-x-3 transition-all duration-500
                           ${publicationsVisible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-10'}`}
                  style={{ transitionDelay: `${index * 100}ms` }}
                >
                  <h4 className="font-bold text-[#2c2416] text-lg mb-3 group-hover:text-[#3d3420] transition-colors">
                    {pub.title}
                  </h4>
                  <p className="text-[#5a4a3a] text-sm mb-2">
                    {pub.authors} ({pub.year})
                  </p>
                  <p className="text-[#5a4a3a] text-sm mb-2">
                    <em>{pub.publisher}</em> 
                    {pub.volume ? `, Vol. ${pub.volume}` : ""} 
                    {pub.pages ? `, pp. ${pub.pages}` : ""}
                  </p>
                  {pub.doi && (
                    <p className="text-sm">
                      DOI:{" "}
                      <a
                        href={`https://doi.org/${pub.doi}`}
                        className="text-blue-600 hover:text-blue-800 hover:underline font-medium transition-colors"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {pub.doi}
                      </a>
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Projects Section */}
        <section 
          id="projects" 
          ref={projectsRef}
          className={`py-20 px-4 sm:px-6 lg:px-8 transition-all duration-1000 ${
            projectsVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
          }`}
        >
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-4xl lg:text-5xl font-bold text-[#2c2416] mb-4">
                Dự Án Tiêu Biểu
              </h2>
              <div className="w-24 h-1 bg-gradient-to-r from-transparent via-[#2c2416] to-transparent mx-auto"></div>
            </div>

            <div className="space-y-6">
              {clubData.projects.map((project, index) => (
                <div
                  key={project.id}
                  onClick={() => router.push(project.projectShowcaseUrl)}
                  className={`group p-8 bg-white/10 backdrop-blur-md rounded-3xl border-l-4 border-[#2c2416]
                           hover:bg-white/20 hover:shadow-2xl hover:border-l-8 
                           transform hover:translate-x-3 hover:scale-[1.02] cursor-pointer 
                           transition-all duration-500 relative overflow-hidden
                           ${projectsVisible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-10'}`}
                  style={{ transitionDelay: `${index * 100}ms` }}
                >
                  {/* Gradient Accent on Hover */}
                  <div className="absolute right-0 top-0 w-32 h-32 bg-gradient-to-br from-[#2c2416]/10 to-transparent 
                                rounded-full blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                  
                  <h3 className="text-2xl font-bold text-[#2c2416] mb-3 group-hover:text-[#3d3420] 
                               flex items-center gap-3 transition-colors relative z-10">
                    <span className="w-2 h-2 rounded-full bg-gradient-to-r from-[#2c2416] to-[#5a4a3a] 
                                   group-hover:scale-150 transition-transform"></span>
                    {project.projectName}
                    <svg className="w-6 h-6 transform group-hover:translate-x-2 transition-transform ml-auto" 
                         fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </h3>
                  <p className="text-[#5a4a3a] leading-relaxed relative z-10">
                    {project.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Vision Section */}
        <section 
          ref={visionRef}
          className={`py-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-transparent to-white/10 transition-all duration-1000 ${
            visionVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
          }`}
        >
          <div className="max-w-5xl mx-auto">
            <div className="p-12 bg-white/10 backdrop-blur-md rounded-3xl border border-white/20 
                         shadow-2xl text-center relative overflow-hidden">
              {/* Decorative Elements */}
              <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-amber-500/10 to-transparent rounded-full blur-3xl"></div>
              <div className="absolute bottom-0 left-0 w-64 h-64 bg-gradient-to-tr from-blue-500/10 to-transparent rounded-full blur-3xl"></div>
              
              <h2 className="text-4xl lg:text-5xl font-bold text-[#2c2416] mb-8 relative z-10">
                Tầm Nhìn
              </h2>
              <div className="space-y-6 text-lg text-[#5a4a3a] relative z-10">
                {[
                  { icon: "🌏", text: "Tri thức được chia sẻ cởi mở và lan tỏa" },
                  { icon: "💪", text: "Sinh viên được trang bị năng lực thực chiến về dữ liệu, cloud, AI và Quantum" },
                  { icon: "🤝", text: "Cộng đồng kết nối giữa giảng đường - doanh nghiệp - xã hội" },
                  { icon: "🇻🇳", text: "Xây dựng năng lực dữ liệu quốc gia của Việt Nam trong kỷ nguyên số", bold: true }
                ].map((item, index) => (
                  <p 
                    key={index}
                    className={`flex items-center justify-center gap-3 transform transition-all duration-500 hover:scale-105
                              ${item.bold ? 'font-bold text-[#2c2416] text-xl' : ''}
                              ${visionVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-5'}`}
                    style={{ transitionDelay: `${index * 150}ms` }}
                  >
                    <span className="text-4xl transform hover:scale-125 transition-transform">{item.icon}</span>
                    <span>{item.text}</span>
                  </p>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Scroll to Top button */}
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="fixed bottom-8 right-8 p-4 bg-gradient-to-r from-[#2c2416] to-[#3d3420] text-white 
                   rounded-full shadow-2xl hover:shadow-3xl transform hover:scale-110 hover:rotate-12
                   transition-all duration-300 border border-white/20 backdrop-blur-sm z-40
                   group"
          aria-label="Scroll to top"
        >
          <svg className="w-6 h-6 transform group-hover:-translate-y-1 transition-transform" 
               fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
          </svg>
        </button>
      </main>
    </div>
  );
}