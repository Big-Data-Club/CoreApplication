"use client";

import React, { useState, useEffect } from 'react';
import formConfig from '@/data/AILearningSurvey.json';

// Declare window.storage type
declare global {
  interface Window {
    storage: {
      get: (key: string, shared?: boolean) => Promise<{ key: string; value: string; shared: boolean } | null>;
      set: (key: string, value: string, shared?: boolean) => Promise<{ key: string; value: string; shared: boolean } | null>;
      delete: (key: string, shared?: boolean) => Promise<{ key: string; deleted: boolean; shared: boolean } | null>;
      list: (prefix?: string, shared?: boolean) => Promise<{ keys: string[]; prefix?: string; shared: boolean } | null>;
    };
  }
}

// Import all question components
import {
  SingleChoiceQuestion,
  MultipleChoiceQuestion,
  ShortAnswerQuestion,
  LongAnswerQuestion,
  NumberQuestion,
  FillInTheBlankQuestion,
  CodeQuestion,
  MatchingQuestion,
  RatingQuestion,
  DateTimeQuestion,
  EmailQuestion,
  MatrixQuestion
} from '@/components/form/QuestionComponents';
import { Button } from '@/components/ui/button';

type Question = {
  id: string;
  type: string;
  question: string;
  required: boolean;
  [key: string]: any;
};

export default function FormPage() {
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const [checkingSubmission, setCheckingSubmission] = useState(true);

  // Load form config
  const formData = formConfig as any;
  const questions: Question[] = formData.questions || [];
  const FORM_SUBMISSION_KEY = `form_submitted_${formData.formId}`;
  
  // Pagination - 5 questions per page
  const questionsPerPage = 6;
  const totalPages = Math.ceil(questions.length / questionsPerPage);
  const currentQuestions = questions.slice(
    currentPage * questionsPerPage,
    (currentPage + 1) * questionsPerPage
  );
  useEffect(() => {
    const checkSubmissionStatus = async () => {
      try {
        const result = await window.storage.get(FORM_SUBMISSION_KEY);
        if (result && result.value === 'true') {
          setHasSubmitted(true);
          setSubmitted(true);
        }
      } catch {
        
      } finally {
        setCheckingSubmission(false);
      }
    };

    checkSubmissionStatus();
  }, [FORM_SUBMISSION_KEY]);

  const handleChange = (questionId: string, value: any) => {
    setAnswers(prev => ({ ...prev, [questionId]: value }));
    
    // Clear error when user starts typing
    if (errors[questionId]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[questionId];
        return newErrors;
      });
    }
  };

  const validatePage = () => {
    const newErrors: Record<string, string> = {};
    
    currentQuestions.forEach(q => {
      if (q.required) {
        const answer = answers[q.id];
        
        // Check if answer is empty
        if (!answer || 
            (Array.isArray(answer) && answer.length === 0) ||
            (typeof answer === 'object' && !Array.isArray(answer) && Object.keys(answer).length === 0) ||
            answer === '') {
          newErrors[q.id] = 'Câu hỏi này là bắt buộc';
        }
        
        // Check matrix questions - ensure all rows are answered
        if (q.type === 'matrix' && typeof answer === 'object' && !Array.isArray(answer)) {
          const answeredRows = Object.keys(answer).length;
          const totalRows = q.rows?.length || 0;
          if (answeredRows < totalRows) {
            newErrors[q.id] = 'Vui lòng đánh giá tất cả các tính năng';
          }
        }
        
        // Check multiple choice constraints
        if (q.type === 'multiple' && Array.isArray(answer)) {
          if (q.constraints?.minChoices && answer.length < q.constraints.minChoices) {
            newErrors[q.id] = `Vui lòng chọn tối thiểu ${q.constraints.minChoices} mục`;
          }
        }
      }
      
      // Email validation
      if (q.type === 'email' && answers[q.id]) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(answers[q.id])) {
          newErrors[q.id] = 'Email không hợp lệ';
        }
      }
      
      // Number validation
      if (q.type === 'number' && answers[q.id] !== undefined && answers[q.id] !== '') {
        const num = parseFloat(answers[q.id]);
        if (q.constraints?.min !== undefined && num < q.constraints.min) {
          newErrors[q.id] = `Giá trị tối thiểu là ${q.constraints.min}`;
        }
        if (q.constraints?.max !== undefined && num > q.constraints.max) {
          newErrors[q.id] = `Giá trị tối đa là ${q.constraints.max}`;
        }
      }
    });
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (validatePage()) {
      setCurrentPage(prev => Math.min(prev + 1, totalPages - 1));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      alert('⚠ Vui lòng điền đầy đủ các câu hỏi bắt buộc trên trang này');
    }
  };

  const handlePrev = () => {
    setCurrentPage(prev => Math.max(prev - 1, 0));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSubmit = async () => {
    // Check if already submitted (double-check)
    try {
      const result = await window.storage.get(FORM_SUBMISSION_KEY);
      if (result && result.value === 'true') {
        alert('⚠️ Bạn đã submit form này rồi!');
        setSubmitted(true);
        setHasSubmitted(true);
        return;
      }
    } catch {
    }

    // Validate current page first
    if (!validatePage()) {
      alert('⚠ Vui lòng điền đầy đủ các câu hỏi bắt buộc');
      return;
    }

    // Validate all required questions across all pages
    let allValid = true;
    const allErrors: Record<string, string> = {};
    
    questions.forEach(q => {
      if (q.required) {
        const answer = answers[q.id];
        if (!answer || 
            (Array.isArray(answer) && answer.length === 0) ||
            (typeof answer === 'object' && !Array.isArray(answer) && Object.keys(answer).length === 0)) {
          allErrors[q.id] = 'Câu hỏi này là bắt buộc';
          allValid = false;
        }
      }
    });

    if (!allValid) {
      setErrors(allErrors);
      // Find first page with error
      for (let i = 0; i < totalPages; i++) {
        const pageQuestions = questions.slice(i * questionsPerPage, (i + 1) * questionsPerPage);
        const hasError = pageQuestions.some(q => allErrors[q.id]);
        if (hasError) {
          setCurrentPage(i);
          window.scrollTo({ top: 0, behavior: 'smooth' });
          break;
        }
      }
      alert('⚠ Vui lòng điền đầy đủ tất cả các câu hỏi bắt buộc');
      return;
    }

    setLoading(true);

    try {
      // Prepare submission data
      const submissionData = {
        formId: formData.formId,
        formTitle: formData.formTitle,
        sheetName: formData.sheetName,
        formType: formData.formType,
        questions: questions,
        answers: answers,
        submittedAt: new Date().toISOString(),
        userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'Unknown'
      };

      const response = await fetch('/api/submit-form', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(submissionData),
      });

      const result = await response.json();

      if (result.success) {
        // Mark as submitted in storage
        try {
          await window.storage.set(FORM_SUBMISSION_KEY, 'true');
        } catch (storageError) {
          console.error('Could not save submission status:', storageError);
        }
        
        setSubmitted(true);
        setHasSubmitted(true);
        console.log('Form submitted successfully');
      } else {
        throw new Error(result.message || 'Submission failed');
      }
    } catch (error) {
      console.error('Submission error:', error);
      alert('❌ Có lỗi xảy ra khi gửi form. Vui lòng thử lại sau.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setAnswers({});
    setErrors({});
    setSubmitted(false);
    setCurrentPage(0);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const renderQuestion = (question: Question) => {
    const props = {
      question,
      value: answers[question.id],
      onChange: handleChange,
      error: errors[question.id]
    };

    switch (question.type) {
      case 'single':
        return <SingleChoiceQuestion key={question.id} {...props} />;
      case 'multiple':
        return <MultipleChoiceQuestion key={question.id} {...props} />;
      case 'short':
        return <ShortAnswerQuestion key={question.id} {...props} />;
      case 'long':
        return <LongAnswerQuestion key={question.id} {...props} />;
      case 'number':
        return <NumberQuestion key={question.id} {...props} />;
      case 'rating':
        return <RatingQuestion key={question.id} {...props} />;
      case 'fillblank':
        return <FillInTheBlankQuestion key={question.id} {...props} />;
      case 'code':
        return <CodeQuestion key={question.id} {...props} />;
      case 'matching':
        return <MatchingQuestion key={question.id} {...props} />;
      case 'date':
      case 'datetime':
      case 'time':
        return <DateTimeQuestion key={question.id} {...props} />;
      case 'email':
        return <EmailQuestion key={question.id} {...props} />;
      case 'matrix':
        return <MatrixQuestion key={question.id} {...props} />;
      default:
        return null;
    }
  };

  // Loading screen while checking submission status
  if (checkingSubmission) {
    return (
      <div className="min-h-screen bg-transparent p-4 flex items-center justify-center">
        <div className="max-w-2xl w-full border-4 border-double border-[#2c2416] bg-transparent p-12 text-center">
          <div className="text-4xl mb-4">⏳</div>
          <p className="text-lg text-[#5a4a3a]">Đang kiểm tra...</p>
        </div>
      </div>
    );
  }

  // Success screen
  if (submitted) {
    return (
      <div className="min-h-screen bg-transparent p-4 flex items-center justify-center">
        <div className="max-w-2xl w-full border-4 border-double border-[#2c2416] bg-transparent p-12 text-center">
          <div className="text-6xl mb-4">✓</div>
          <h2 className="text-3xl font-bold text-[#2c2416] mb-4 font-serif">
            {formData.thankYouMessage || 'Cảm ơn bạn!'}
          </h2>
          <p className="text-lg text-[#5a4a3a] mb-6">
            {hasSubmitted && !formData.allowMultipleSubmissions 
              ? 'Bạn đã submit form này trước đó rồi.'
              : 'Câu trả lời của bạn đã được ghi nhận thành công.'}
          </p>
          <p className="text-sm text-[#5a4a3a] mb-8 italic">
            Form: {formData.formTitle}
          </p>
          <div className="bg-[#f5f1e8] border-l-4 border-[#2c2416] p-4 mb-6 text-left">
            <p className="text-sm text-[#2c2416] font-semibold mb-2">📊 Dữ liệu của bạn sẽ được sử dụng để:</p>
            <ul className="text-sm text-[#5a4a3a] space-y-1 list-disc list-inside">
              <li>Xác định roadmap phát triển tính năng</li>
              <li>Phân tích nhu cầu theo nhóm đối tượng</li>
              <li>Cải thiện trải nghiệm học tập cho sinh viên</li>
            </ul>
          </div>
          {formData.allowMultipleSubmissions && (
            <Button
              onClick={handleReset}
              className="px-8 py-3 bg-[#2c2416] text-[#f5f1e8] font-semibold border-2 border-[#2c2416] hover:bg-[#5a4a3a] transition-colors"
            >
              Gửi câu trả lời khác
            </Button>
          )}
        </div>
      </div>
    );
  }

  // Main form
  return (
    <div className="min-h-screen bg-transparent p-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="border-4 border-double border-[#2c2416] bg-transparent p-8 mb-8 text-center">
          <h1 className="text-4xl font-bold text-[#2c2416] mb-2">
            {formData.formTitle}
          </h1>
          <p className="text-[#5a4a3a] italic mb-4">
            {formData.formDescription}
          </p>
          <div className="flex justify-center items-center gap-2 text-sm text-[#5a4a3a]">
            <span className="text-red-600">*</span>
            <span>Câu hỏi bắt buộc</span>
          </div>
          
          {/* Progress indicator */}
          {totalPages > 1 && (
            <div className="mt-4">
              <div className="flex justify-center gap-2">
                {Array.from({ length: totalPages }, (_, i) => (
                  <div
                    key={i}
                    className={`w-8 h-2 ${
                      i === currentPage ? 'bg-[#2c2416]' : 'bg-[#d4caba]'
                    } border border-[#2c2416]`}
                  />
                ))}
              </div>
              <p className="text-xs text-[#5a4a3a] mt-2">
                Trang {currentPage + 1} / {totalPages}
              </p>
            </div>
          )}
        </div>

        {/* Questions */}
        <div>
          {currentQuestions.map(q => renderQuestion(q))}
        </div>

        {/* Navigation Buttons */}
        <div className="flex justify-between items-center gap-4 mt-8 mb-8">
          {/* Previous Button */}
          {currentPage > 0 ? (
            <Button
              onClick={handlePrev}
              className="px-6 py-3 border-2 border-[#2c2416] bg-transparent text-[#2c2416] font-semibold hover:bg-[#f5f1e8] transition-colors"
            >
              ← Trang trước
            </Button>
          ) : (
            <div></div>
          )}

          {/* Reset Button */}
          <Button
            onClick={handleReset}
            className="px-6 py-2 border border-[#5a4a3a] bg-transparent text-[#5a4a3a] text-sm hover:bg-[#f5f1e8] transition-colors"
          >
            Xóa toàn bộ
          </Button>

          {/* Next/Submit Button */}
          {currentPage < totalPages - 1 ? (
            <Button
              onClick={handleNext}
              className="px-6 py-3 bg-[#2c2416] text-[#f5f1e8] font-semibold border-2 border-[#2c2416] hover:bg-[#5a4a3a] transition-colors"
            >
              Trang tiếp theo →
            </Button>
          ) : (
            <Button
              onClick={handleSubmit}
              disabled={loading}
              className={`px-8 py-3 bg-[#2c2416] text-[#f5f1e8] font-semibold border-2 border-[#2c2416] transition-colors ${
                loading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-[#5a4a3a]'
              }`}
            >
              {loading ? 'Đang gửi...' : 'Gửi Câu Trả Lời'}
            </Button>
          )}
        </div>

        {/* Footer info */}
        <div className="text-center mt-8 text-sm text-[#5a4a3a] italic border-t-2 border-[#2c2416] pt-4">
          <p>Dữ liệu được mã hóa và bảo mật tuyệt đối</p>
          <p className="mt-2">© 2026 AI LMS Survey • Phát triển sản phẩm dựa trên nhu cầu thực tế</p>
        </div>
      </div>
    </div>
  );
}