"use client";

import React, { useState } from "react";
import {
  Calendar,
  ExternalLink,
  User,
  MoreVertical,
  Edit2,
  Trash2,
  AlertCircle,
} from "lucide-react";
import { Task, User as UserType, EventItem, PRIORITY_COLORS } from "@/types";
import { formatDate } from "@/utils/utils";
import { useAuth } from "@/hooks/useAuth";
import Image from "next/image";

interface TaskCardProps {
  task: Task;
  users: UserType[];
  events: EventItem[];
  onEdit: (task: Task) => void;
  onDelete: (taskId: number | string) => void;
  onDragStart: (e: React.DragEvent, task: Task) => void;
}

const TaskCard: React.FC<TaskCardProps> = ({
  task,
  users,
  events,
  onEdit,
  onDelete,
  onDragStart,
}) => {
  const [showMenu, setShowMenu] = useState(false);
  const { canEditTask } = useAuth();
  const assignedUsers = users.filter((u) =>
    task.assignees.some((assigneeId) => assigneeId.toString() === u.id.toString())
  );
  const associatedEvent = task.event || events.find(
    (e) => e.id.toString() === task.eventId?.toString()
  );

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, task)}
      className="bg-white rounded-lg p-4 shadow-sm border border-gray-200 hover:shadow-md transition-shadow cursor-move mb-3 relative"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <h4 className="font-semibold text-gray-800 text-sm flex-1 pr-2">
          {task.title}
        </h4>
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="text-gray-400 hover:text-gray-600 p-1"
        >
          <MoreVertical size={16} />
        </button>

        {/* Menu Dropdown */}
        {showMenu && (
          <div className="absolute right-2 top-8 bg-white shadow-lg rounded-md border border-gray-200 z-10 py-1">
            {canEditTask && (<button
              onClick={() => {
                onEdit(task);
                setShowMenu(false);
              }}
              className="flex items-center gap-2 px-4 py-2 hover:bg-gray-50 text-sm w-full text-left"
            >
              <Edit2 size={14} /> Edit
            </button>)
            }
            <button
              onClick={() => {
                onDelete(task.id);
                setShowMenu(false);
              }}
              className="flex items-center gap-2 px-4 py-2 hover:bg-gray-50 text-sm w-full text-left text-red-600"
            >
              <Trash2 size={14} /> Delete
            </button>
          </div>
        )}
      </div>

      {/* Priority Badge */}
      {task.priority && (
        <div className="mb-2">
          <span
            className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded border ${
              PRIORITY_COLORS[task.priority]
            }`}
          >
            <AlertCircle size={12} />
            {task.priority}
          </span>
        </div>
      )}

      {/* Event Badge */}
      {associatedEvent && (
        <div className="mb-3">
          <span className="inline-block px-2 py-1 text-xs font-medium text-blue-800 bg-blue-100 rounded">
            Event: {associatedEvent.title}
          </span>
        </div>
      )}

      {/* Description */}
      <p className="text-gray-600 text-xs mb-3 line-clamp-3">
        {task.description}
      </p>

      {/* Assignees */}
      {assignedUsers.length > 0 && (
        <div className="flex items-center gap-2 mb-2">
          <User size={14} className="text-gray-400" />
          <div className="flex -space-x-2">
            {assignedUsers.map((user) => (
              <div
                key={user.id}
                className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white text-xs font-medium border-2 border-white overflow-hidden"
                title={`${user.name} (${user.team})`}
              >
                <Image src={user.profilePicture ? `${user.profilePicture}` : `https://api.dicebear.com/9.x/adventurer/svg?seed=${user?.name}`}
                  alt={user.name}
                  width={28}
                  height={28}
                  className="object-cover"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Links */}
      {task.links && task.links.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {task.links.map((link) => (
            <a
              key={link.id}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 bg-blue-50 px-2 py-1 rounded"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink size={12} />
              {link.title}
            </a>
          ))}
        </div>
      )}

      {/* Dates */}
      {(task.startDate || task.endDate) && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Calendar size={12} />
          <span>
            {formatDate(task.startDate)}
            {task.startDate && task.endDate && " → "}
            {formatDate(task.endDate)}
          </span>
        </div>
      )}

      {/* Created/Updated Info */}
      {(task.createdBy || task.updatedBy) && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <div className="text-xs text-gray-400 space-y-1">
            {task.createdBy && (
              <div>
                Created by: <span className="font-medium">{task.createdBy.name}</span>
              </div>
            )}
            {task.updatedBy && (
              <div>
                Updated by: <span className="font-medium">{task.updatedBy.name}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TaskCard;