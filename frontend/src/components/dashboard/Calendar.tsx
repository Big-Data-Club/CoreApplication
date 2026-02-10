import React, { useState } from 'react';
import { Calendar, ChevronLeft, ChevronRight, Clock, Users, Link2, X, Check, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { TaskResponse } from '@/services/taskService';
import { useCalendarTasks } from '@/hooks/useCalendarTasks';

type ViewMode = 'day' | 'week' | 'month';

type TaskWithColor = TaskResponse & { 
  color: string;
  eventName?: string;
  status: 'todo' | 'in-progress' | 'done' | 'cancel';
};

interface TaskCardProps {
  task: TaskWithColor;
  onClick: () => void;
  spanInfo: { isStart: boolean; isEnd: boolean };
}

interface DetailPanelProps {
  task: TaskWithColor;
  onClose: () => void;
}

interface TaskRow {
  task: TaskWithColor;
  startIdx: number;
  endIdx: number;
  span: number;
}

const ModernCalendar = () => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [viewMode, setViewMode] = useState<ViewMode>('month');
  const [selectedTask, setSelectedTask] = useState<TaskWithColor | null>(null);

  // Fetch tasks from API
  const { tasks: mockTasks, loading, error, refreshTasks } = useCalendarTasks();

  const priorityConfig = {
    LOW: { color: 'bg-green-500', label: 'Low', icon: '●' },
    MEDIUM: { color: 'bg-yellow-500', label: 'Medium', icon: '●●' },
    HIGH: { color: 'bg-orange-500', label: 'High', icon: '●●●' },
    CRITICAL: { color: 'bg-red-500', label: 'Critical', icon: '🔥' }
  };

  const statusConfig = {
    'todo': { color: 'bg-gray-500', label: 'To Do', icon: '○' },
    'in-progress': { color: 'bg-blue-500', label: 'In Progress', icon: '◐' },
    'done': { color: 'bg-green-500', label: 'Done', icon: '●' },
    'cancel': { color: 'bg-red-500', label: 'Cancelled', icon: '✕' }
  };

  // Helper functions
  const goToToday = () => setCurrentDate(new Date());
  
  const navigate = (direction: number) => {
    const newDate = new Date(currentDate);
    if (viewMode === 'day') {
      newDate.setDate(newDate.getDate() + direction);
    } else if (viewMode === 'week') {
      newDate.setDate(newDate.getDate() + (direction * 7));
    } else {
      newDate.setMonth(newDate.getMonth() + direction);
    }
    setCurrentDate(newDate);
  };

  const getCalendarTitle = () => {
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'];
    
    if (viewMode === 'day') {
      return `${monthNames[currentDate.getMonth()]} ${currentDate.getDate()}, ${currentDate.getFullYear()}`;
    } else if (viewMode === 'week') {
      const startOfWeek = new Date(currentDate);
      startOfWeek.setDate(currentDate.getDate() - currentDate.getDay());
      const endOfWeek = new Date(startOfWeek);
      endOfWeek.setDate(startOfWeek.getDate() + 6);
      return `${monthNames[startOfWeek.getMonth()]} ${startOfWeek.getDate()} - ${monthNames[endOfWeek.getMonth()]} ${endOfWeek.getDate()}, ${currentDate.getFullYear()}`;
    } else {
      return `${monthNames[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
    }
  };

  const getDaysInView = (): Date[] => {
    if (viewMode === 'day') {
      return [currentDate];
    } else if (viewMode === 'week') {
      const days: Date[] = [];
      const startOfWeek = new Date(currentDate);
      startOfWeek.setDate(currentDate.getDate() - currentDate.getDay());
      for (let i = 0; i < 7; i++) {
        const day = new Date(startOfWeek);
        day.setDate(startOfWeek.getDate() + i);
        days.push(day);
      }
      return days;
    } else {
      const days: Date[] = [];
      const firstDay = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      const startDate = new Date(firstDay);
      startDate.setDate(startDate.getDate() - startDate.getDay());
      
      for (let i = 0; i < 42; i++) {
        const day = new Date(startDate);
        day.setDate(startDate.getDate() + i);
        days.push(day);
      }
      return days;
    }
  };

  const parseDate = (dateStr: string | Date | undefined): Date | null => {
    if (!dateStr) return null;
    if (dateStr instanceof Date) return dateStr;
    return new Date(dateStr);
  };

  const getTasksForDay = (day: Date): TaskWithColor[] => {
    return mockTasks.filter(task => {
      const taskStart = parseDate(task.startDate);
      const taskEnd = parseDate(task.endDate);
      if (!taskStart || !taskEnd) return false;

      const dayTime = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
      const startTime = new Date(taskStart.getFullYear(), taskStart.getMonth(), taskStart.getDate()).getTime();
      const endTime = new Date(taskEnd.getFullYear(), taskEnd.getMonth(), taskEnd.getDate()).getTime();
      
      return dayTime >= startTime && dayTime <= endTime;
    });
  };

  const getTaskSpanInfo = (task: TaskWithColor, day: Date) => {
    const taskStart = parseDate(task.startDate);
    const taskEnd = parseDate(task.endDate);
    if (!taskStart || !taskEnd) return { isStart: false, isEnd: false };

    const startDay = new Date(taskStart.getFullYear(), taskStart.getMonth(), taskStart.getDate());
    const endDay = new Date(taskEnd.getFullYear(), taskEnd.getMonth(), taskEnd.getDate());
    const currentDay = new Date(day.getFullYear(), day.getMonth(), day.getDate());
    
    const isStart = startDay.getTime() === currentDay.getTime();
    const isEnd = endDay.getTime() === currentDay.getTime();
    
    return { isStart, isEnd };
  };

  const getTaskRows = (): TaskRow[] => {
    if (viewMode === 'day') return [];
    
    const rows: TaskRow[] = [];
    const placedTasks = new Set<number>();
    const days = getDaysInView();
    
    days.forEach(day => {
      const dayTasks = getTasksForDay(day);
      dayTasks.forEach(task => {
        if (placedTasks.has(task.id as number)) return;
        
        const taskStart = parseDate(task.startDate);
        if (!taskStart) return;

        const startDay = new Date(taskStart.getFullYear(), taskStart.getMonth(), taskStart.getDate());
        const currentDay = new Date(day.getFullYear(), day.getMonth(), day.getDate());
        
        if (startDay.getTime() === currentDay.getTime()) {
          const taskEnd = parseDate(task.endDate);
          if (!taskEnd) return;

          const endDay = new Date(taskEnd.getFullYear(), taskEnd.getMonth(), taskEnd.getDate());
          const startIdx = days.findIndex(d => 
            d.getFullYear() === startDay.getFullYear() && 
            d.getMonth() === startDay.getMonth() && 
            d.getDate() === startDay.getDate()
          );
          const endIdx = days.findIndex(d =>
            d.getFullYear() === endDay.getFullYear() &&
            d.getMonth() === endDay.getMonth() &&
            d.getDate() === endDay.getDate()
          );
          
          if (startIdx >= 0 && endIdx >= 0) {
            rows.push({
              task,
              startIdx,
              endIdx,
              span: endIdx - startIdx + 1
            });
            placedTasks.add(task.id as number);
          }
        }
      });
    });
    
    return rows;
  };

  // Components
  const TaskCard: React.FC<TaskCardProps> = ({ task, onClick, spanInfo }) => {
    const { isStart, isEnd } = spanInfo;
    
    return (
      <div
        onClick={onClick}
        className={`group p-1 rounded-md cursor-pointer transition-all duration-200 hover:scale-[1.01] hover:shadow-md w-fit max-w-full`}
        style={{ 
          backgroundColor: isStart ? (task.color + '20') : (task.color + '10'),
          borderLeft: isStart ? `2px solid ${task.color}` : 'none',
          borderRight: isEnd ? `2px solid ${task.color}` : 'none',
          borderTop: `1px solid ${task.color}`,
          borderBottom: `1px solid ${task.color}`
        }}
      >
        <div className="flex items-start justify-between gap-1">
          <div className="flex-1">
            {isStart && (
              <>
                <p className="text-xs font-medium text-gray-900 whitespace-normal break-words group-hover:text-gray-700">
                  {task.title}
                </p>
                <p className="text-xs text-gray-600 mt-0.5">
                  {parseDate(task.startDate)?.getHours()}:{parseDate(task.startDate)?.getMinutes().toString().padStart(2, '0')}
                </p>
              </>
            )}
          </div>
          {isStart && (
            <span className={`${priorityConfig[task.priority || 'MEDIUM'].color} w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1`} />
          )}
        </div>
      </div>
    );
  };

  const DetailPanel: React.FC<DetailPanelProps> = ({ task, onClose }) => {
    return (
      <div className="fixed right-0 top-0 h-full w-96 bg-white shadow-2xl z-50 animate-slide-in-right overflow-y-auto">
        <div className="sticky top-0 bg-gradient-to-r from-purple-600 to-blue-600 text-white p-6 z-10">
          <div className="flex items-start justify-between mb-4">
            <h2 className="text-2xl font-bold flex-1 pr-4">{task.title}</h2>
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors flex-shrink-0"
            >
              <X size={20} />
            </button>
          </div>
          
          <div className="flex items-center gap-3 text-sm">
            <span className={`${statusConfig[task.status || 'todo'].color} px-3 py-1 rounded-full text-white font-medium`}>
              {statusConfig[task.status || 'todo'].icon} {statusConfig[task.status || 'todo'].label}
            </span>
            <span className={`${priorityConfig[task.priority || 'MEDIUM'].color} px-3 py-1 rounded-full text-white font-medium`}>
              {priorityConfig[task.priority || 'MEDIUM'].icon} {priorityConfig[task.priority || 'MEDIUM'].label}
            </span>
          </div>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
              <AlertCircle size={16} className="text-purple-600" />
              Description
            </h3>
            <p className="text-sm text-gray-600 leading-relaxed bg-gray-50 p-4 rounded-lg">
              {task.description}
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">Event</h3>
            <div 
              className="px-4 py-3 rounded-lg font-medium text-white"
              style={{ backgroundColor: task.color }}
            >
              {task.eventName || task.event?.title}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
              <Clock size={16} className="text-purple-600" />
              Schedule
            </h3>
            <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-4 rounded-lg space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Start:</span>
                <span className="font-medium text-gray-900">
                  {parseDate(task.startDate)?.toLocaleString('vi-VN', { 
                    month: 'short', 
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">End:</span>
                <span className="font-medium text-gray-900">
                  {parseDate(task.endDate)?.toLocaleString('vi-VN', { 
                    month: 'short', 
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </span>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <Users size={16} className="text-purple-600" />
              Assignees ({task.assignees?.length || 0})
            </h3>
            <div className="space-y-2">
              {task.assignees?.map((assignee) => (
                <div
                  key={assignee.id}
                  className="flex items-center gap-3 p-3 bg-gradient-to-r from-gray-50 to-gray-100 rounded-lg hover:from-purple-50 hover:to-blue-50 transition-colors"
                >
                  <div className="text-2xl">👤</div>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900">{assignee.name}</p>
                    <p className="text-xs text-gray-600">{assignee.team}</p>
                  </div>
                  <Check size={16} className="text-green-600" />
                </div>
              ))}
            </div>
          </div>

          {task.links && task.links.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <Link2 size={16} className="text-purple-600" />
                Resources ({task.links.length})
              </h3>
              <div className="space-y-2">
                {task.links.map((link, idx: number) => (
                  <a
                    key={idx}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 p-3 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg hover:from-blue-100 hover:to-purple-100 transition-colors group"
                  >
                    <Link2 size={16} className="text-blue-600 group-hover:rotate-12 transition-transform" />
                    <span className="text-sm text-blue-700 font-medium group-hover:underline flex-1">
                      {link.title}
                    </span>
                    <span className="text-xs text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity">
                      Open →
                    </span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const days = getDaysInView();
  const taskRows = getTaskRows();

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-transparent p-3 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-gray-600">Loading calendar...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-transparent p-3 flex items-center justify-center">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <h3 className="text-red-800 font-semibold mb-2">Error Loading Calendar</h3>
          <p className="text-red-600 mb-4">{error}</p>
          <button
            onClick={refreshTasks}
            className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2"
          >
            <RefreshCw size={18} />
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-auto bg-transparent p-3">
      <style>{`
        @keyframes slide-in-right {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.3s ease-out;
        }
      `}</style>

      <div className="max-w-full mx-auto">
        {/* Header */}
        <div className="bg-white/80 backdrop-blur-xl rounded-2xl shadow-lg p-3 mb-4 border border-white/50">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="p-1.5 bg-gradient-to-br from-purple-600 to-blue-600 rounded-lg shadow-md">
                <Calendar className="text-white" size={20} />
              </div>
              <div>
                <h1 className="text-lg font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
                  Task Calendar
                </h1>
              </div>
            </div>

            {/* Navigation & View Mode */}
            <div className="flex items-center gap-2">
              {/* View Mode Selector */}
              <div className="flex gap-1 bg-gray-100 p-0.5 rounded-lg">
                {['day', 'week', 'month'].map(mode => (
                  <button
                    key={mode}
                    onClick={() => setViewMode(mode as ViewMode)}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-all duration-200 ${
                      viewMode === mode
                        ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white shadow-md'
                        : 'text-gray-600 hover:text-gray-900 hover:bg-white'
                    }`}
                  >
                    {mode.charAt(0).toUpperCase() + mode.slice(1)}
                  </button>
                ))}
              </div>

              {/* Navigation Buttons */}
              <div className="flex items-center gap-1">
                <button
                  onClick={() => navigate(-1)}
                  className="p-1 hover:bg-purple-100 rounded-lg transition-colors"
                >
                  <ChevronLeft size={18} className="text-purple-600" />
                </button>
                <button
                  onClick={goToToday}
                  className="px-3 py-1 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg font-medium text-xs hover:shadow-md transition-shadow"
                >
                  Today
                </button>
                <button
                  onClick={() => navigate(1)}
                  className="p-1 hover:bg-purple-100 rounded-lg transition-colors"
                >
                  <ChevronRight size={18} className="text-purple-600" />
                </button>
                <button
                  onClick={refreshTasks}
                  className="p-1 hover:bg-purple-100 rounded-lg transition-colors ml-2"
                  title="Refresh tasks"
                >
                  <RefreshCw size={18} className="text-purple-600" />
                </button>
              </div>
            </div>

            {/* Calendar Title */}
            <h2 className="text-sm font-bold text-gray-800 whitespace-nowrap">{getCalendarTitle()}</h2>
          </div>
        </div>

        {/* Calendar Grid */}
        <div className="bg-white/80 backdrop-blur-xl rounded-2xl shadow-lg overflow-hidden border border-white/50">
          {/* Week Header */}
          {viewMode !== 'day' && (
            <div className={`grid ${viewMode === 'week' ? 'grid-cols-7' : 'grid-cols-7'} bg-gradient-to-r from-purple-600 to-blue-600`}>
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                <div key={day} className="py-2 text-center text-white font-semibold text-xs">
                  {day}
                </div>
              ))}
            </div>
          )}

          {/* Calendar Body */}
          <div className={`grid ${viewMode === 'week' ? 'grid-cols-7' : viewMode === 'month' ? 'grid-cols-7' : 'grid-cols-1'} gap-0 divide-x divide-y divide-gray-200`}>
            {days.map((day, idx) => {
              const allDayTasks = getTasksForDay(day);
              const dayStartingTasks = allDayTasks.filter(task => {
                const taskStart = parseDate(task.startDate);
                const startDay = new Date((taskStart?.getFullYear() || 0), (taskStart?.getMonth() || 0), (taskStart?.getDate() || 0));
                const currentDay = new Date(day.getFullYear(), day.getMonth(), day.getDate());
                return startDay.getTime() === currentDay.getTime();
              });
              
              const isToday = day.toDateString() === new Date().toDateString();
              const isCurrentMonth = day.getMonth() === currentDate.getMonth();
              
              return (
                <div
                  key={idx}
                  className={`min-h-20 p-2 transition-colors ${
                    viewMode === 'month' && !isCurrentMonth ? 'bg-gray-50' : 'bg-white hover:bg-purple-50/30'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-semibold ${
                      isToday 
                        ? 'w-6 h-6 flex items-center justify-center bg-gradient-to-br from-purple-600 to-blue-600 text-white rounded-full'
                        : isCurrentMonth ? 'text-gray-900' : 'text-gray-400'
                    }`}>
                      {day.getDate()}
                    </span>
                    {allDayTasks.length > 0 && (
                      <span className="text-xs bg-purple-600 text-white px-1.5 py-0.5 rounded-full font-medium">
                        {allDayTasks.length}
                      </span>
                    )}
                  </div>
                  <div className="space-y-0.5">
                    {dayStartingTasks.map(task => {
                      const spanInfo = getTaskSpanInfo(task, day);
                      return (
                        <TaskCard
                          key={task.id}
                          task={task}
                          spanInfo={spanInfo}
                          onClick={() => setSelectedTask(task)}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Multi-day task rows for week/month view */}
          {(viewMode === 'week' || viewMode === 'month') && taskRows.length > 0 && (
            <div className="bg-gray-50 border-t border-gray-200">
              <div className="text-xs font-semibold text-gray-600 p-2 bg-gray-100 border-b border-gray-200">
                Multi-day Tasks
              </div>
              <div className="p-2 space-y-1">
                {taskRows.map((row, rowIdx) => {
                  const { task, startIdx, span } = row;
                  const colWidthPercent = (span / 7) * 100;
                  const offsetPercent = (startIdx / 7) * 100;
                  
                  return (
                    <div
                      key={rowIdx}
                      onClick={() => setSelectedTask(task)}
                      className="group cursor-pointer transition-all duration-200 hover:shadow-md rounded-md"
                      style={{
                        marginLeft: `${offsetPercent}%`,
                        width: `${colWidthPercent}%`,
                        backgroundColor: task.color + '20',
                        border: `1px solid ${task.color}`,
                        borderLeft: `3px solid ${task.color}`,
                        padding: '0.375rem'
                      }}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-gray-900 truncate group-hover:text-gray-700">
                            {task.title}
                          </p>
                          <p className="text-xs text-gray-600 mt-0.5">
                            {parseDate(task.startDate)?.toLocaleDateString('vi-VN', { month: 'short', day: 'numeric' })} - {parseDate(task.endDate)?.toLocaleDateString('vi-VN', { month: 'short', day: 'numeric' })}
                          </p>
                        </div>
                        <span className={`${priorityConfig[task.priority || 'MEDIUM'].color} w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1`} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="mt-3 bg-white/80 backdrop-blur-xl rounded-2xl shadow-lg p-4 border border-white/50">
          <h3 className="text-xs font-semibold text-gray-700 mb-2">Priority Levels</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(priorityConfig).map(([key, config]) => (
              <div key={key} className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${config.color}`} />
                <span className="text-xs text-gray-700">{config.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Detail Panel Overlay */}
      {selectedTask && (
        <>
          <div
            className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40"
            onClick={() => setSelectedTask(null)}
          />
          <DetailPanel task={selectedTask} onClose={() => setSelectedTask(null)} />
        </>
      )}
    </div>
  );
};

export { ModernCalendar };
