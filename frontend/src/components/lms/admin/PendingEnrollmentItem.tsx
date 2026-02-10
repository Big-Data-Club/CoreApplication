"use client";

export function PendingEnrollmentItem({ studentName, courseName, time }: { studentName: string; courseName: string; time: string }) {
  return (
    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
      <div className="flex-1">
        <p className="font-medium text-gray-800 text-sm">{studentName}</p>
        <p className="text-xs text-gray-600">{courseName}</p>
      </div>
      <span className="text-xs text-gray-500">{time}</span>
    </div>
  );
}