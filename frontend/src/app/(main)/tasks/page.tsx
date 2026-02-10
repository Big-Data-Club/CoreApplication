/* eslint-disable @typescript-eslint/no-unused-vars */
"use client";

import React, { useState, useEffect } from "react";
import { Plus, Loader2, RefreshCw } from "lucide-react";
import TaskModal from "@/components/Board/Task/TaskModal";
import BoardColumn from "@/components/Board/Column/BoardColumn";
import { Column, Task, User } from "@/types";
import { useTasks } from "@/hooks/useTasks";
import { useEvents } from "@/hooks/useEvents";
import { userService } from "@/services/userService";
import { TaskRequest } from "@/services/taskService";
import TutorialGuide from '@/components/ui/TutorialGuide';
import { tutorialConfig } from '@/config/tutorials';

const KanbanBoard: React.FC = () => {
  const [columns, setColumns] = useState<Column[]>([
    { id: "todo", title: "TODO", color: "bg-slate-500", tasks: [] },
    { id: "in-progress", title: "In Progress", color: "bg-blue-500", tasks: [] },
    { id: "done", title: "Done", color: "bg-green-500", tasks: [] },
    { id: "cancel", title: "Cancel", color: "bg-red-500", tasks: [] },
  ]);
  
  const [users, setUsers] = useState<User[]>([]);
  const [draggedTask, setDraggedTask] = useState<Task | null>(null);
  const [modalState, setModalState] = useState<{
    isOpen: boolean;
    task: Task | null;
    columnId: string | null;
  }>({ isOpen: false, task: null, columnId: null });
  const [newColumnName, setNewColumnName] = useState("");
  const [showNewColumn, setShowNewColumn] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<number>(1);

  const {
    tasks,
    loading: tasksLoading,
    error: tasksError,
    createTask,
    updateTask,
    moveTask,
    deleteTask,
    fetchTasks,
  } = useTasks();

  const {
    events,
    loading: eventsLoading,
  } = useEvents();

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const usersData = await userService.getAll();
        setUsers(
          usersData.map((u) => ({
            id: u.id,
            name: u.name,
            email: u.email,
            code: u.code,
            team: u.team,
            type: u.type,
            role: u.role,
            score: u.totalScore,
            totalScore: u.totalScore,
            active: u.active,
            status: u.active,
            profilePicture: u.profilePicture,
          }))
        );
      } catch (error) {
        console.error("Failed to fetch users:", error);
      }
    };

    fetchUsers();
  }, []);

  useEffect(() => {
    setColumns((prevColumns) =>
      prevColumns.map((col) => ({
        ...col,
        tasks: tasks.filter((task) => task.columnId === col.id),
      }))
    );
  }, [tasks]);

  const handleDragStart = (e: React.DragEvent, task: Task) => {
    setDraggedTask(task);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = async (e: React.DragEvent, targetColumnId: string) => {
    e.preventDefault();
    if (!draggedTask || draggedTask.columnId === targetColumnId) {
      setDraggedTask(null);
      return;
    }

    try {
      const taskId = Number(draggedTask.id);
      await moveTask(taskId, targetColumnId, currentUserId);
      setDraggedTask(null);
    } catch (error) {
      console.error("Failed to move task:", error);
      alert("Failed to move task. Please try again.");
      await fetchTasks();
    }
  };

  const handleAddTask = (columnId: string) => {
    setModalState({ isOpen: true, task: null, columnId });
  };

  const handleEditTask = (task: Task) => {
    setModalState({ isOpen: true, task, columnId: task.columnId });
  };

  const handleSaveTask = async (taskData: any) => {
    try {
      const taskRequest: TaskRequest = {
        title: taskData.title,
        description: taskData.description,
        priority: taskData.priority,
        columnId: taskData.columnId,
        startDate: taskData.startDate || undefined,
        endDate: taskData.endDate || undefined,
        eventId: taskData.eventId || undefined,
        assigneeIds: taskData.assignees.map((id: any) => Number(id)),
        links: taskData.links.map((link: any) => ({
          url: link.url,
          title: link.title,
        })),
      };

      if (modalState.task) {
        const taskId = Number(modalState.task.id);
        await updateTask(taskId, taskRequest, currentUserId);
      } else {
        await createTask(taskRequest, currentUserId);
      }

      setModalState({ isOpen: false, task: null, columnId: null });
    } catch (error: any) {
      throw new Error(error.message || "Failed to save task");
    }
  };

  const handleDeleteTask = async (taskId: number | string) => {
    if (!confirm("Are you sure you want to delete this task?")) return;

    try {
      await deleteTask(Number(taskId));
    } catch (error) {
      console.error("Failed to delete task:", error);
      alert("Failed to delete task. Please try again.");
    }
  };

  const handleAddColumn = () => {
    if (!newColumnName.trim()) return;

    const colors = [
      "bg-purple-500",
      "bg-pink-500",
      "bg-yellow-500",
      "bg-indigo-500",
      "bg-teal-500",
    ];
    const randomColor = colors[Math.floor(Math.random() * colors.length)];

    setColumns([
      ...columns,
      {
        id: newColumnName.toLowerCase().replace(/\s+/g, "-"),
        title: newColumnName,
        color: randomColor,
        tasks: [],
      },
    ]);

    setNewColumnName("");
    setShowNewColumn(false);
  };

  const handleDeleteColumn = (columnId: string) => {
    const column = columns.find((col) => col.id === columnId);
    if (column && column.tasks.length > 0) {
      if (
        !confirm(
          `This column has ${column.tasks.length} task(s). Are you sure you want to delete it?`
        )
      ) {
        return;
      }
    }

    setColumns(columns.filter((col) => col.id !== columnId));
  };

  const handleRefresh = async () => {
    await fetchTasks();
  };

  if (tasksLoading || eventsLoading) {
    return (
      <div className="min-h-screen bg-transparent p-6 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-gray-600">Loading board...</p>
        </div>
      </div>
    );
  }

  if (tasksError) {
    return (
      <div className="min-h-screen bg-transparent p-6 flex items-center justify-center">
        <div className="text-center">
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
            <h3 className="text-red-800 font-semibold mb-2">Error Loading Board</h3>
            <p className="text-red-600 mb-4">{tasksError}</p>
            <button
              onClick={handleRefresh}
              className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-transparent p-4 sm:p-6 lg:p-8" id="tasks-page">
      <div className="max-w-[1600px] mx-auto">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between" id="tasks-header">
          <div>
            <h1 className="text-4xl font-bold text-gray-800 mb-2">BDC Board</h1>
            <p className="text-gray-600">
              {tasks.length} task{tasks.length !== 1 ? "s" : ""} • {events.length}{" "}
              event{events.length !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            title="Refresh board"
          >
            <RefreshCw size={18} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Board Columns */}
        <div className="flex gap-4 overflow-x-auto pb-4" id="tasks-columns">
          {columns.map((column) => (
            <BoardColumn
              key={column.id}
              column={column}
              users={users}
              events={events}
              onAddTask={handleAddTask}
              onEditTask={handleEditTask}
              onDeleteTask={handleDeleteTask}
              onDeleteColumn={handleDeleteColumn}
              onDragStart={handleDragStart}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
            />
          ))}

          {/* Add Column Button */}
          {!showNewColumn ? (
            <button
              onClick={() => setShowNewColumn(true)}
              className="min-w-[320px] h-[200px] bg-white bg-opacity-50 border-2 border-dashed border-gray-300 rounded-xl flex items-center justify-center hover:bg-opacity-70 hover:border-gray-400 transition-all"
            >
              <div className="text-center">
                <Plus size={32} className="mx-auto text-gray-400 mb-2" />
                <span className="text-gray-600 font-medium">Add Column</span>
              </div>
            </button>
          ) : (
            <div className="min-w-[320px] bg-white rounded-xl p-4">
              <input
                type="text"
                value={newColumnName}
                onChange={(e) => setNewColumnName(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleAddColumn()}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg mb-3"
                placeholder="Column name..."
                autoFocus
              />
              <div className="flex gap-2">
                <button
                  onClick={handleAddColumn}
                  className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
                >
                  Add
                </button>
                <button
                  onClick={() => {
                    setShowNewColumn(false);
                    setNewColumnName("");
                  }}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Task Modal */}
      {modalState.isOpen && (
        <TaskModal
          task={modalState.task}
          columnId={modalState.columnId}
          users={users}
          events={events}
          onSave={handleSaveTask}
          onClose={() => setModalState({ isOpen: false, task: null, columnId: null })}
        />
      )}

      {/* Tutorial Guide Component */}
      <TutorialGuide 
        steps={tutorialConfig.tasks}
        onComplete={() => {}}
      />
    </div>
  );
};

export default KanbanBoard;