'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { lmsService } from '@/services/lmsService';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Loader, Upload } from 'lucide-react';

interface Course {
  id: number;
  title: string;
  description: string;
}

interface Learner {
  id: number;
  student_id: number;
  student_name: string;
  student_email: string;
  status: 'WAITING' | 'ACCEPTED' | 'REJECTED';
  enrolled_at: string;
  accepted_at?: string;
  rejected_at?: string;
}

type StatusFilter = 'ALL' | 'WAITING' | 'ACCEPTED' | 'REJECTED';

export default function CourseLearnerPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = parseInt(params.courseId as string);

  const [course, setCourse] = useState<Course | null>(null);
  const [learners, setLearners] = useState<Learner[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [showBulkImport, setShowBulkImport] = useState(false);

  useEffect(() => {
    loadCourse();
    loadLearners();
  }, [courseId]);

  useEffect(() => {
    if (courseId) {
      loadLearners();
    }
  }, [statusFilter, courseId]);

  const loadCourse = async () => {
    try {
      const data = await lmsService.getCourse(courseId);
      setCourse(data?.data);
    } catch (error) {
      console.error('Failed to load course:', error);
    }
  };

  const loadLearners = async () => {
    try {
      setLoading(true);
      const status = statusFilter === 'ALL' ? undefined : statusFilter;
      const data = await lmsService.getCourseLearners(courseId, status);
      setLearners(data || []);
      console.log(data)
    } catch (error) {
      console.error('Failed to load learners:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async (enrollmentId: number) => {
    try {
      setProcessingId(enrollmentId);
      await lmsService.acceptEnrollment(enrollmentId, courseId);
      await loadLearners();
    } catch (error: any) {
      alert(error.response?.data?.message || 'Lỗi khi chấp nhận đơn');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (enrollmentId: number) => {
    if (!confirm('Bạn chắc chắn muốn từ chối đơn này?')) return;

    try {
      setProcessingId(enrollmentId);
      await lmsService.rejectEnrollment(enrollmentId, courseId);
      await loadLearners();
    } catch (error: any) {
      alert(error.response?.data?.message || 'Lỗi khi từ chối đơn');
    } finally {
      setProcessingId(null);
    }
  };

  const handleBulkEnroll = async (studentIds: number[]) => {
    try {
      setLoading(true);
      await lmsService.bulkEnroll(courseId, studentIds);
      alert('Đã thêm học viên thành công');
      setShowBulkImport(false);
      await loadLearners();
    } catch (error: any) {
      alert(error.response?.data?.message || 'Lỗi khi thêm học viên');
    } finally {
      setLoading(false);
    }
  };

  const statusCounts = {
    WAITING: learners.filter(l => l.status === 'WAITING').length,
    ACCEPTED: learners.filter(l => l.status === 'ACCEPTED').length,
    REJECTED: learners.filter(l => l.status === 'REJECTED').length,
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'WAITING':
        return <span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-medium rounded-full">Chờ xác nhận</span>;
      case 'ACCEPTED':
        return <span className="px-3 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full">Đã chấp nhận</span>;
      case 'REJECTED':
        return <span className="px-3 py-1 bg-red-100 text-red-800 text-xs font-medium rounded-full">Từ chối</span>;
      default:
        return null;
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
        <div className="flex justify-between items-start">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <Button
                onClick={() => router.push(`/lms/teacher/courses/${courseId}`)}
                variant="outline"
                size="sm"
              >
                ← Quay lại khóa học
              </Button>
            </div>
            <h1 className="text-3xl font-bold text-gray-900">{course?.title}</h1>
            <p className="text-gray-600 mt-1">Quản lý học viên</p>
          </div>
          <Button
            onClick={() => setShowBulkImport(!showBulkImport)}
            className="flex items-center gap-2"
          >
            <Upload className="w-4 h-4" />
            Thêm hàng loạt
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="space-y-6">
        {/* Bulk Import Section */}
        {showBulkImport && (
          <Card className="p-6 border-blue-200 bg-blue-50">
            <h2 className="text-lg font-semibold mb-4">Thêm học viên hàng loạt</h2>
            <BulkImportForm onSubmit={handleBulkEnroll} loading={loading} />
          </Card>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="p-4">
            <p className="text-sm text-gray-600 mb-1">Tổng cộng</p>
            <p className="text-3xl font-bold">{learners.length}</p>
          </Card>
          <Card className="p-4 border-yellow-200 bg-yellow-50">
            <p className="text-sm text-gray-600 mb-1">Chờ xác nhận</p>
            <p className="text-3xl font-bold text-yellow-700">{statusCounts.WAITING}</p>
          </Card>
          <Card className="p-4 border-green-200 bg-green-50">
            <p className="text-sm text-gray-600 mb-1">Đã chấp nhận</p>
            <p className="text-3xl font-bold text-green-700">{statusCounts.ACCEPTED}</p>
          </Card>
          <Card className="p-4 border-red-200 bg-red-50">
            <p className="text-sm text-gray-600 mb-1">Từ chối</p>
            <p className="text-3xl font-bold text-red-700">{statusCounts.REJECTED}</p>
          </Card>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-4 border-b bg-white rounded-t-lg p-4">
          {[
            { id: 'ALL', label: 'Tất cả' },
            { id: 'WAITING', label: `Chờ xác nhận (${statusCounts.WAITING})` },
            { id: 'ACCEPTED', label: `Đã chấp nhận (${statusCounts.ACCEPTED})` },
            { id: 'REJECTED', label: `Từ chối (${statusCounts.REJECTED})` },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id as StatusFilter)}
              className={`px-4 py-3 font-medium border-b-2 transition-colors ${
                statusFilter === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Learners List */}
        <div className="bg-white rounded-b-lg">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader className="animate-spin w-8 h-8" />
            </div>
          ) : learners.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              Không có học viên nào
            </div>
          ) : (
            <div className="divide-y">
              {learners.map((learner) => (
                <div key={learner.id} className="p-4 hover:bg-gray-50 transition-colors flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                      <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-sm font-semibold text-blue-700">
                        {learner.student_name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-semibold text-gray-800">{learner.student_name}</p>
                        <p className="text-sm text-gray-600">{learner.student_email}</p>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <div>
                      {getStatusBadge(learner.status)}
                      <p className="text-xs text-gray-500 mt-1">
                        {learner.enrolled_at ? new Date(learner.enrolled_at).toLocaleDateString('vi-VN') : ''}
                      </p>
                    </div>

                    {learner.status === 'WAITING' && (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => handleAccept(learner.id)}
                          disabled={processingId === learner.id}
                          className="bg-green-600 hover:bg-green-700"
                        >
                          {processingId === learner.id ? (
                            <Loader className="w-4 h-4 animate-spin" />
                          ) : (
                            'Chấp nhận'
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleReject(learner.id)}
                          disabled={processingId === learner.id}
                        >
                          Từ chối
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface BulkImportFormProps {
  onSubmit: (studentIds: number[]) => void;
  loading: boolean;
}

const BulkImportForm = ({ onSubmit, loading }: BulkImportFormProps) => {
  const [studentIds, setStudentIds] = useState('');

  const handleSubmit = () => {
    const ids = studentIds
      .split('\n')
      .map(id => parseInt(id.trim()))
      .filter(id => !isNaN(id));

    if (ids.length === 0) {
      alert('Vui lòng nhập ít nhất một ID học viên');
      return;
    }

    onSubmit(ids);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-2">ID học viên (mỗi dòng một ID)</label>
        <textarea
          value={studentIds}
          onChange={(e) => setStudentIds(e.target.value)}
          placeholder="1&#10;2&#10;3"
          className="w-full p-3 border rounded-lg font-mono text-sm"
          rows={6}
          disabled={loading}
        />
      </div>
      <div className="flex gap-2">
        <Button
          onClick={handleSubmit}
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-700"
        >
          {loading ? (
            <>
              <Loader className="w-4 h-4 mr-2 animate-spin" />
              Đang xử lý...
            </>
          ) : (
            'Thêm học viên'
          )}
        </Button>
      </div>
    </div>
  );
};
