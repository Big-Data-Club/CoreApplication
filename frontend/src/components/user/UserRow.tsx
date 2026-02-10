"use client";
import React from "react";
import { User } from "@/types";
import Avatar from "./Avatar";

export default function UserRow({ user, onClick, onToggleStatus }: { user: User; onClick: (u: User) => void; onToggleStatus: (id: string | number) => void; }) {
  return (
    <div
      className="bg-white rounded-lg shadow-md grid grid-cols-12 gap-2 sm:gap-4 items-center px-3 sm:px-6 py-3 sm:py-4 hover:shadow-lg transition cursor-pointer overflow-x-auto min-w-max sm:min-w-full text-xs sm:text-sm overflow-x-auto"
      onClick={() => onClick(user)}
    >
      <div className="col-span-5 flex items-center gap-2 sm:gap-4">
        <Avatar code={user.code} size={32} />
        <div className="min-w-0">
          <div className="font-semibold text-sm sm:text-lg truncate">{user.name}</div>
          <div className="text-xs sm:text-sm text-gray-500 truncate">{user.email}</div>
        </div>
      </div>

      <div className="col-span-1 text-center text-sm">{user.role}</div>
      <div className="col-span-1 text-center text-sm">{user.team}</div>
      <div className="col-span-1 text-center text-sm">{user.score}</div>
      <div className="col-span-2 text-center text-sm">{user.dateAdded ? new Date(user.dateAdded).toLocaleDateString() : "Chưa xác định"}</div>

      <div className="col-span-2 flex items-center justify-center gap-2 sm:gap-4">
        <label className="inline-flex items-center cursor-pointer select-none">
          <input
            type="checkbox"
            checked={Boolean(user.status)}
            onClick={(e) => { e.stopPropagation(); onToggleStatus(user.id); }}
            readOnly
            className="form-checkbox h-5 w-10 rounded-full appearance-none bg-gray-200 checked:bg-blue-600 relative"
            style={{ display: "inline-block" }}
          />
        </label>

        <button
          onClick={(e) => { e.stopPropagation(); onClick(user); }}
          className="text-sm text-blue-600 underline"
        >
          Details
        </button>
      </div>
    </div>
  );
}
