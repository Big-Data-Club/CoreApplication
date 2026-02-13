import axios, { AxiosInstance } from 'axios';

const LMS_API_URL = process.env.NEXT_PUBLIC_LMS_API_URL || 'http://localhost:8081/api/v1';

class QuizService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: LMS_API_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.api.interceptors.request.use((config) => {
      const token = this.getAuthToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

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
  // QUIZ MANAGEMENT (Teacher)
  // ============================================

  async createQuizWithContent(contentId: number, quizData: any) {
    // Tạo một bản sao để xử lý dữ liệu
    const payload = { 
        ...quizData,
        content_id: contentId 
    };

    // XỬ LÝ DATE: Chuyển sang ISO string
    if (payload.available_from) {
        payload.available_from = new Date(payload.available_from).toISOString();
    }
    if (payload.available_until) {
        payload.available_until = new Date(payload.available_until).toISOString();
    }

    // Đảm bảo các trường số là number (đề phòng input trả về string)
    if (payload.time_limit_minutes) payload.time_limit_minutes = Number(payload.time_limit_minutes);
    if (payload.max_attempts) payload.max_attempts = Number(payload.max_attempts);
    if (payload.passing_score) payload.passing_score = Number(payload.passing_score);
    if (payload.total_points) payload.total_points = Number(payload.total_points);

    const response = await this.api.post('/quizzes', payload);
    return response.data;
  }

  async createQuiz(quizData: any) {
    const response = await this.api.post('/quizzes', quizData);
    return response.data;
  }

  async getQuiz(quizId: number) {
    const response = await this.api.get(`/quizzes/${quizId}`);
    return response.data;
  }

  async getQuizByContentId(contentId: number) {
    const response = await this.api.get(`/content/${contentId}/quiz`);
    return response.data;
  }

  async updateQuiz(quizId: number, updates: any) {
    const response = await this.api.put(`/quizzes/${quizId}`, updates);
    return response.data;
  }

  async deleteQuiz(quizId: number) {
    const response = await this.api.delete(`/quizzes/${quizId}`);
    return response.data;
  }

  // ============================================
  // QUESTION MANAGEMENT (Teacher)
  // ============================================

  async createQuestion(quizId: number, questionData: any) {
    const data = { ...questionData, quiz_id: quizId };
    const response = await this.api.post(`/quizzes/${quizId}/questions`, data);
    return response.data;
  }

  async updateQuestion(questionId: number, updates: any) {
    const response = await this.api.put(`/questions/${questionId}`, updates);
    return response.data;
  }

  async deleteQuestion(questionId: number) {
    const response = await this.api.delete(`/questions/${questionId}`);
    return response.data;
  }

  async listQuestions(quizId: number) {
    const response = await this.api.get(`/quizzes/${quizId}/questions`);
    return response.data;
  }

  // ============================================
  // STUDENT QUIZ OPERATIONS
  // ============================================

  async startQuizAttempt(quizId: number) {
    const response = await this.api.post(`/quizzes/${quizId}/start`);
    return response.data;
  }

  async submitAnswer(attemptId: number, answerData: any) {
    const response = await this.api.post(`/attempts/${attemptId}/answers`, answerData);
    return response.data;
  }

  async submitQuiz(attemptId: number) {
    const response = await this.api.post(`/attempts/${attemptId}/submit`);
    return response.data;
  }

  async getQuizResult(attemptId: number) {
    const response = await this.api.get(`/attempts/${attemptId}/result`);
    return response.data;
  }

  async reviewQuiz(attemptId: number) {
    const response = await this.api.get(`/attempts/${attemptId}/review`);
    return response.data;
  }

  // ============================================
  // GRADING OPERATIONS (Teacher)
  // ============================================

  async gradeAnswer(answerId: number, gradeData: any) {
    const response = await this.api.post(`/answers/${answerId}/grade`, gradeData);
    return response.data;
  }

  async bulkGrade(quizId: number, grades: any[]) {
    const response = await this.api.post(`/quizzes/${quizId}/bulk-grade`, { grades });
    return response.data;
  }

  async listAnswersForGrading(quizId: number) {
    const response = await this.api.get(`/quizzes/${quizId}/grading`);
    return response.data;
  }

  // ============================================
  // QUESTION IMAGE OPERATIONS
  // ============================================

  async uploadQuestionImage(questionId: number, file: File) {
    const formData = new FormData();
    formData.append('image', file);
    
    const response = await this.api.post(
      `/questions/${questionId}/images`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  }

  async listQuestionImages(questionId: number) {
    const response = await this.api.get(`/questions/${questionId}/images`);
    return response.data;
  }

  async deleteQuestionImage(questionId: number, imageId: number | string) {
    const response = await this.api.delete(`/questions/${questionId}/images/${imageId}`);
    return response.data;
  }

  // ============================================
  // QUIZ HISTORY OPERATIONS
  // ============================================

  async getMyQuizAttempts(quizId: number) {
    const response = await this.api.get(`/quizzes/${quizId}/my-attempts`);
    return response.data;
  }

  async getAttemptSummary(attemptId: number) {
    const response = await this.api.get(`/attempts/${attemptId}/summary`);
    return response.data;
  }
}

export const quizService = new QuizService();
export default quizService;