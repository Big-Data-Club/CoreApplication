import axios, { AxiosInstance } from 'axios';

const LMS_API_URL = process.env.NEXT_PUBLIC_LMS_API_URL || 'http://localhost:8081/api/v1';

class LMSService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: LMS_API_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add auth token interceptor
    this.api.interceptors.request.use((config) => {
      const token = this.getAuthToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle errors globally
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  private getAuthToken(): string | null {
    const cookies = document.cookie.split(';');
    const authCookie = cookies.find(c => c.trim().startsWith('authToken='));
    return authCookie ? authCookie.split('=')[1] : null;
  }

  // ============================================
  // USER MANAGEMENT
  // ============================================

  async getMyRoles() {
    const response = await this.api.get('/me/roles');
    return response.data?.data?.roles;
  }

  // ============================================
  // COURSE MANAGEMENT
  // ============================================

  async createCourse(courseData: {
    title: string;
    description?: string;
    category?: string;
    level?: string;
    thumbnail_url?: string;
  }) {
    const response = await this.api.post('/courses', courseData);
    return response.data;
  }

  async getCourse(courseId: number) {
    const response = await this.api.get(`/courses/${courseId}`);
    return response.data;
  }

  async updateCourse(courseId: number, updates: {
    title?: string;
    description?: string;
    category?: string;
    level?: string;
    thumbnail_url?: string;
  }) {
    const response = await this.api.put(`/courses/${courseId}`, updates);
    return response.data;
  }

  async deleteCourse(courseId: number) {
    const response = await this.api.delete(`/courses/${courseId}`);
    return response.data;
  }

  async publishCourse(courseId: number) {
    const response = await this.api.post(`/courses/${courseId}/publish`);
    return response.data;
  }

  async listMyCourses(params?: { status?: string; page?: number; page_size?: number }) {
    const response = await this.api.get('/courses/my', { params });
    return response.data;
  }

  async listPublishedCourses(params?: { 
    category?: string; 
    level?: string; 
    search?: string;
    page?: number; 
    page_size?: number;
  }) {
    const response = await this.api.get('/courses', { params });
    return response.data?.data;
  }

  // ============================================
  // SECTION MANAGEMENT
  // ============================================

  async createSection(courseId: number, sectionData: {
    title: string;
    description?: string;
    order_index: number;
  }) {
    const response = await this.api.post(`/courses/${courseId}/sections`, sectionData);
    return response.data;
  }

  async getSection(sectionId: number) {
    const response = await this.api.get(`/sections/${sectionId}`);
    return response.data;
  }

  async listSections(courseId: number) {
    const response = await this.api.get(`/courses/${courseId}/sections`);
    return response.data;
  }

  async updateSection(sectionId: number, updates: {
    title?: string;
    description?: string;
    order_index?: number;
    is_published?: boolean;
  }) {
    const response = await this.api.put(`/sections/${sectionId}`, updates);
    return response.data;
  }

  async deleteSection(sectionId: number) {
    const response = await this.api.delete(`/sections/${sectionId}`);
    return response.data;
  }

  // ============================================
  // CONTENT MANAGEMENT
  // ============================================

  async createContent(sectionId: number, contentData: {
    type: 'TEXT' | 'VIDEO' | 'DOCUMENT' | 'IMAGE' | 'QUIZ' | 'FORUM' | 'ANNOUNCEMENT';
    title: string;
    description?: string;
    order_index: number;
    metadata?: Record<string, any>;
    is_mandatory?: boolean;
  }) {
    const response = await this.api.post(`/sections/${sectionId}/content`, contentData);
    return response.data;
  }

  async getContent(contentId: number) {
    const response = await this.api.get(`/content/${contentId}`);
    return response.data;
  }

  async listContent(sectionId: number) {
    const response = await this.api.get(`/sections/${sectionId}/content`);
    return response.data;
  }

  async updateContent(contentId: number, updates: {
    title?: string;
    description?: string;
    order_index?: number;
    metadata?: Record<string, any>;
    is_published?: boolean;
    is_mandatory?: boolean;
  }) {
    const response = await this.api.put(`/content/${contentId}`, updates);
    return response.data;
  }

  async deleteContent(contentId: number) {
    const response = await this.api.delete(`/content/${contentId}`);
    return response.data;
  }

  // ============================================
  // ENROLLMENT MANAGEMENT
  // ============================================

  async enrollCourse(courseId: number) {
    const response = await this.api.post('/enrollments', { course_id: courseId });
    return response.data;
  }

  async getMyEnrollments(status?: 'WAITING' | 'ACCEPTED' | 'REJECTED') {
    const params = status ? { status } : {};
    const response = await this.api.get('/enrollments/my', { params });
    return response.data?.data;
  }

  async getCourseLearners(courseId: number, status?: 'WAITING' | 'ACCEPTED' | 'REJECTED') {
    const params = status ? { status } : {};
    const response = await this.api.get(`/courses/${courseId}/learners`, { params });
    return response.data?.data;
  }

  async acceptEnrollment(enrollmentId: number, courseId: number) {
    const response = await this.api.put(`/enrollments/${enrollmentId}/accept`, { course_id: courseId });
    return response.data;
  }

  async rejectEnrollment(enrollmentId: number, courseId: number) {
    const response = await this.api.put(`/enrollments/${enrollmentId}/reject`, { course_id: courseId });
    return response.data;
  }

  async bulkEnroll(courseId: number, studentIds: number[]) {
    const response = await this.api.post(`/courses/${courseId}/bulk-enroll`, { student_ids: studentIds });
    return response.data;
  }

  async cancelEnrollment(enrollmentId: number) {
    const response = await this.api.delete(`/enrollments/${enrollmentId}`);
    return response.data;
  }
}

export const lmsService = new LMSService();
export default lmsService;