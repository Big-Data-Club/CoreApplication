"use client";

import React, { useState, useEffect, useMemo } from "react";
import { Trophy, Medal, Award, TrendingUp } from "lucide-react";
import { userService } from "@/services/userService";
import type { UserResponse } from "@/services/userService";
import TutorialGuide from '@/components/ui/TutorialGuide';
import { tutorialConfig } from '@/config/tutorials';

const LeaderboardPage = () => {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        setLoading(true);
        const data = await userService.getAll();
        setUsers(data);
      } catch (error) {
        console.error("Failed to fetch users:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchUsers();
  }, []);

  // Sort users by score
  const sortedUsers = useMemo(() => {
    return [...users]
      .filter(u => u.active)
      .sort((a, b) => (b.totalScore || 0) - (a.totalScore || 0));
  }, [users]);

  const top5 = sortedUsers.slice(0, 5);
  const remaining = sortedUsers.slice(5);

  const getTrophyIcon = (rank: number) => {
    switch (rank) {
      case 1:
        return { icon: Trophy, color: "text-yellow-500", bg: "bg-yellow-500/10" };
      case 2:
      case 3:
        return { icon: Medal, color: "text-gray-400", bg: "bg-gray-400/10" };
      case 4:
      case 5:
        return { icon: Award, color: "text-orange-600", bg: "bg-orange-600/10" };
      default:
        return { icon: Trophy, color: "text-gray-300", bg: "bg-gray-300/10" };
    }
  };

  const getPodiumHeight = (rank: number) => {
    switch (rank) {
      case 1: return "h-48";
      case 2: return "h-40";
      case 3: return "h-38";
      case 4: return "h-32";
      case 5: return "h-30";
      default: return "h-24";
    }
  };

  const getPodiumOrder = () => {
    if (top5.length < 5) return top5;
    return [top5[1], top5[0], top5[2], top5[3], top5[4]];
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading leaderboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-transparent p-4 sm:p-6 lg:p-8" id="leaderboard-page">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8 sm:mb-12" id="leaderboard-header">
          <div className="flex items-center justify-center gap-2 sm:gap-3 mb-2 sm:mb-4 flex-wrap">
            <TrendingUp className="h-8 w-8 sm:h-10 sm:w-10 lg:h-12 lg:w-12 text-purple-600" />
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
              Leaderboard
            </h1>
          </div>
          <p className="text-sm sm:text-base lg:text-lg text-gray-600">Top performers and rankings</p>
        </div>

        {/* Top 5 Podium */}
        <div className="mb-16" id="leaderboard-podium">
          <h2 className="text-2xl font-bold text-center mb-8 text-gray-800">Top 5 Champions</h2>
          <div className="flex items-end justify-center gap-4 px-4">
            {getPodiumOrder().map((user, idx) => {
              const actualRank = top5.findIndex(u => u.id === user.id) + 1;
              const trophy = getTrophyIcon(actualRank);
              const Icon = trophy.icon;

              return (
                <div
                  key={user.id}
                  className={`flex flex-col items-center ${
                    actualRank === 1 ? "order-2" : actualRank === 2 ? "order-1" : actualRank === 3 ? "order-3" : actualRank === 4 ? "order-4" : "order-5"
                  }`}
                >
                  {/* User Info */}
                  <div className="mb-4 text-center">
                    <div className={`w-20 h-20 rounded-full ${trophy.bg} ${trophy.color} flex items-center justify-center mb-3 mx-auto border-4 border-white shadow-lg`}>
                      <Icon className="h-10 w-10" />
                    </div>
                    <div className={`text-3xl font-bold mb-1 ${
                      actualRank === 1 ? "text-yellow-600" : 
                      actualRank === 2 || actualRank === 3 ? "text-gray-500" : 
                      "text-orange-600"
                    }`}>
                      #{actualRank}
                    </div>
                    <div className="font-semibold text-gray-800 mb-1 max-w-[120px] truncate">
                      {user.name}
                    </div>
                    <div className="text-sm text-gray-600 mb-1">{user.team}</div>
                    <div className="text-xs text-gray-500">{user.code}</div>
                  </div>

                  {/* Podium */}
                  <div
                    className={`w-32 ${getPodiumHeight(actualRank)} ${
                      actualRank === 1
                        ? "bg-gradient-to-b from-yellow-400 to-yellow-600"
                        : actualRank === 2 || actualRank === 3
                        ? "bg-gradient-to-b from-gray-300 to-gray-500"
                        : "bg-gradient-to-b from-orange-400 to-orange-600"
                    } rounded-t-2xl shadow-2xl flex flex-col items-center justify-center text-white relative overflow-hidden`}
                  >
                    <div className="absolute inset-0 bg-white/10"></div>
                    <div className="relative z-10">
                      <div className="text-3xl font-bold mb-1">{user.totalScore}</div>
                      <div className="text-sm opacity-90">points</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Remaining Rankings */}
        {remaining.length > 0 && (
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-center mb-6 text-gray-800">Other Rankings</h2>
            <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
              <div className="divide-y divide-gray-100">
                {remaining.map((user, idx) => {
                  const rank = idx + 6;
                  return (
                    <div
                      key={user.id}
                      className="flex items-center justify-between p-5 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center gap-4 flex-1">
                        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center font-bold text-gray-700 text-lg">
                          #{rank}
                        </div>
                        <div className="flex-1">
                          <div className="font-semibold text-gray-800">{user.name}</div>
                          <div className="text-sm text-gray-500">
                            {user.code} • {user.team} • {user.type}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-purple-600">
                          {user.totalScore}
                        </div>
                        <div className="text-xs text-gray-500">points</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Empty State */}
        {sortedUsers.length === 0 && (
          <div className="text-center py-12">
            <Trophy className="h-16 w-16 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 text-lg">No rankings available yet</p>
          </div>
        )}
      </div>

      {/* Tutorial Guide Component */}
      <TutorialGuide 
        steps={tutorialConfig.leaderboard}
        onComplete={() => {}}
      />
    </div>
  );
};

export default LeaderboardPage;