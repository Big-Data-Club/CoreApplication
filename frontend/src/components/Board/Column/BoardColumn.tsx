"use client";

import React from "react";
import { Plus, X } from "lucide-react";
import TaskCard from "@/components/Board/Task/TaskCard";
import { Column, User, EventItem, Task } from "@/types";

interface BoardColumnProps {
  column: Column;
  users: User[];
  events: EventItem[];
  onAddTask: (columnId: string) => void;
  onEditTask: (task: Task) => void;
  onDeleteTask: (taskId: number | string) => void;
  onDeleteColumn: (columnId: string) => void;
  onDragStart: (e: React.DragEvent, task: Task) => void;
  onDrop: (e: React.DragEvent, columnId: string) => void;
  onDragOver: (e: React.DragEvent) => void;
}

const BoardColumn: React.FC<BoardColumnProps> = ({
  column,
  users,
  events,
  onAddTask,
  onEditTask,
  onDeleteTask,
  onDeleteColumn,
  onDragStart,
  onDrop,
  onDragOver,
}) => {
  const isDefaultColumn = ["todo", "in-progress", "done", "cancel"].includes(
    column.id.toLowerCase()
  );

  return (
    <div
      onDragOver={onDragOver}
      onDrop={(e) => onDrop(e, column.id)}
      className="bg-gray-50 rounded-xl p-4 min-w-[320px] max-w-[320px] flex flex-col"
    >
      {/* Column Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${column.color}`}></div>
          <h3 className="font-bold text-gray-800">{column.title}</h3>
          <span className="bg-gray-200 text-gray-600 text-xs px-2 py-1 rounded-full">
            {column.tasks.length}
          </span>
        </div>
        {!isDefaultColumn && (
          <button
            onClick={() => onDeleteColumn(column.id)}
            className="text-gray-400 hover:text-red-500 p-1"
            title="Delete column"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Tasks List */}
      <div className="flex-1 overflow-y-auto mb-3 min-h-[200px]">
        {column.tasks.length > 0 ? (
          column.tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              users={users}
              events={events}
              onEdit={onEditTask}
              onDelete={onDeleteTask}
              onDragStart={onDragStart}
            />
          ))
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-400 text-sm">No tasks yet</p>
          </div>
        )}
      </div>

      {/* Add Task Button */}
      <button
        onClick={() => onAddTask(column.id)}
        className="flex items-center justify-center gap-2 w-full py-2 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded-lg transition-colors"
      >
        <Plus size={16} />
        <span className="text-sm font-medium">Add Task</span>
      </button>
    </div>
  );
};

export default BoardColumn;