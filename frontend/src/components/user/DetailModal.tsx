"use client";
import React from "react";
import { User } from "@/types";
import Avatar from "./Avatar";

export default function DetailModal({ user, onClose }: { user: User | null; onClose: () => void; }) {
  if (!user) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Avatar code={user.code} size={56} />
            <div>
              <div className="text-lg font-semibold">{user.name}</div>
              <div className="text-sm text-gray-500">{user.email}</div>
            </div>
          </div>
        </div>

        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500">Code</div>
              <div className="font-medium">{user.code}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Role</div>
              <div className="font-medium">{user.role}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Team</div>
              <div className="font-medium">{user.team}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Type</div>
              <div className="font-medium">{user.type}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Score</div>
              <div className="font-medium">{user.score}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Date added</div>
              <div className="font-medium">{user.dateAdded?new Date(user.dateAdded).toLocaleDateString():"Chưa xác định"}</div>
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500">Status</div>
            <div className="font-medium">{user.status ? "Active" : "Inactive"}</div>
          </div>
        </div>

        <div className="flex justify-end gap-3 p-4 border-t">
          <button onClick={onClose} className="px-3 py-1 rounded bg-blue-600 text-white">Close</button>
        </div>
      </div>
    </div>
  );
}
