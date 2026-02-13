/**
 * Utility functions cho Fill-in-the-Blank questions
 */

import {
  FillBlankTextSettings,
  FillBlankTextCorrectAnswer,
  FillBlankDropdownSettings,
  FillBlankDropdownOption,
  FillBlankValidationError,
  BlankPosition,
} from '@/fillBlankType';

// ============================================
// BLANK DETECTION & PARSING
// ============================================

/**
 * Detect và đếm số lượng blanks trong question text
 */
export function countBlanks(questionText: string): number {
  const matches = questionText.match(/\{BLANK_\d+\}/g);
  return matches ? matches.length : 0;
}

/**
 * Extract blank IDs từ question text
 * Returns mảng các blank IDs đã được sort
 */
export function extractBlankIds(questionText: string): number[] {
  const matches = questionText.match(/\{BLANK_(\d+)\}/g);
  if (!matches) return [];

  const ids = matches.map(match => {
    const idMatch = match.match(/\d+/);
    return idMatch ? parseInt(idMatch[0]) : 0;
  });

  // Remove duplicates và sort
  return Array.from(new Set(ids)).sort((a, b) => a - b);
}

/**
 * Parse question text và trả về positions của tất cả blanks
 */
export function parseBlankPositions(questionText: string): BlankPosition[] {
  const positions: BlankPosition[] = [];
  const regex = /\{BLANK_(\d+)\}/g;
  let match;

  while ((match = regex.exec(questionText)) !== null) {
    const blankId = parseInt(match[1]);
    positions.push({
      blank_id: blankId,
      start_index: match.index,
      end_index: match.index + match[0].length,
      placeholder: match[0],
    });
  }

  return positions;
}

/**
 * Thay thế blanks trong text bằng values
 * Useful cho preview
 */
export function replaceBlanksWithValues(
  questionText: string,
  values: Record<number, string>
): string {
  let result = questionText;
  
  Object.entries(values).forEach(([blankId, value]) => {
    const placeholder = `{BLANK_${blankId}}`;
    result = result.replace(new RegExp(placeholder, 'g'), value || '___');
  });
  
  return result;
}

// ============================================
// VALIDATION
// ============================================

/**
 * Validate Fill Blank Text question
 */
export function validateFillBlankText(
  questionText: string,
  settings: FillBlankTextSettings,
  correctAnswers: FillBlankTextCorrectAnswer[]
): FillBlankValidationError[] {
  const errors: FillBlankValidationError[] = [];

  // Check question text không rỗng
  if (!questionText.trim()) {
    errors.push({
      field: 'question_text',
      message: 'Câu hỏi không được để trống',
    });
  }

  // Detect actual blank count
  const detectedBlanks = extractBlankIds(questionText);
  const detectedCount = detectedBlanks.length;

  // Check có ít nhất 1 blank
  if (detectedCount === 0) {
    errors.push({
      field: 'question_text',
      message: 'Câu hỏi phải có ít nhất 1 chỗ trống (sử dụng {BLANK_1}, {BLANK_2}...)',
    });
    return errors; // Return sớm vì không có blank để validate
  }

  // Check blank count khớp
  if (settings.blank_count !== detectedCount) {
    errors.push({
      field: 'settings',
      message: `Số lượng blank không khớp: phát hiện ${detectedCount}, khai báo ${settings.blank_count}`,
    });
  }

  // Check settings.blanks có đủ không
  if (settings.blanks.length !== detectedCount) {
    errors.push({
      field: 'settings.blanks',
      message: `Thiếu thông tin cho một số blanks. Cần ${detectedCount}, có ${settings.blanks.length}`,
    });
  }

  // Check mỗi blank phải có ít nhất 1 correct answer
  detectedBlanks.forEach(blankId => {
    const answersForBlank = correctAnswers.filter(
      ans => ans.blank_id === blankId && ans.answer_text.trim()
    );

    if (answersForBlank.length === 0) {
      errors.push({
        field: 'correct_answers',
        message: `Blank ${blankId} chưa có đáp án đúng`,
        blank_id: blankId,
      });
    }
  });

  return errors;
}

/**
 * Validate Fill Blank Dropdown question
 */
export function validateFillBlankDropdown(
  questionText: string,
  settings: FillBlankDropdownSettings,
  options: FillBlankDropdownOption[]
): FillBlankValidationError[] {
  const errors: FillBlankValidationError[] = [];

  // Check question text không rỗng
  if (!questionText.trim()) {
    errors.push({
      field: 'question_text',
      message: 'Câu hỏi không được để trống',
    });
  }

  // Detect actual blank count
  const detectedBlanks = extractBlankIds(questionText);
  const detectedCount = detectedBlanks.length;

  // Check có ít nhất 1 blank
  if (detectedCount === 0) {
    errors.push({
      field: 'question_text',
      message: 'Câu hỏi phải có ít nhất 1 chỗ trống (sử dụng {BLANK_1}, {BLANK_2}...)',
    });
    return errors;
  }

  // Check blank count khớp
  if (settings.blank_count !== detectedCount) {
    errors.push({
      field: 'settings',
      message: `Số lượng blank không khớp: phát hiện ${detectedCount}, khai báo ${settings.blank_count}`,
    });
  }

  // Check mỗi blank phải có ít nhất 2 options và đúng 1 correct answer
  detectedBlanks.forEach(blankId => {
    const optionsForBlank = options.filter(opt => opt.blank_id === blankId);

    if (optionsForBlank.length < 2) {
      errors.push({
        field: 'answer_options',
        message: `Blank ${blankId} phải có ít nhất 2 options (hiện có ${optionsForBlank.length})`,
        blank_id: blankId,
      });
    }

    const correctOptions = optionsForBlank.filter(opt => opt.is_correct);

    if (correctOptions.length === 0) {
      errors.push({
        field: 'answer_options',
        message: `Blank ${blankId} chưa có đáp án đúng`,
        blank_id: blankId,
      });
    } else if (correctOptions.length > 1) {
      errors.push({
        field: 'answer_options',
        message: `Blank ${blankId} chỉ được có 1 đáp án đúng (hiện có ${correctOptions.length})`,
        blank_id: blankId,
      });
    }

    // Check option_text không được rỗng
    optionsForBlank.forEach((opt, idx) => {
      if (!opt.option_text.trim()) {
        errors.push({
          field: 'answer_options',
          message: `Option ${idx + 1} của blank ${blankId} không được để trống`,
          blank_id: blankId,
        });
      }
    });
  });

  return errors;
}

// ============================================
// DATA TRANSFORMATION
// ============================================

/**
 * Convert từ frontend data sang backend DTO format
 */
export function prepareFillBlankTextForAPI(
  questionText: string,
  settings: FillBlankTextSettings,
  correctAnswers: FillBlankTextCorrectAnswer[],
  points: number,
  orderIndex: number
) {
  return {
    question_type: 'FILL_BLANK_TEXT',
    question_text: questionText,
    settings: settings,
    points: points,
    order_index: orderIndex,
    is_required: true,
    correct_answers: correctAnswers.map(ans => ({
      blank_id: ans.blank_id,
      answer_text: ans.answer_text,
      case_sensitive: ans.case_sensitive,
      exact_match: ans.exact_match,
      blank_position: ans.blank_position,
    })),
  };
}

/**
 * Convert từ frontend data sang backend DTO format
 */
export function prepareFillBlankDropdownForAPI(
  questionText: string,
  settings: FillBlankDropdownSettings,
  options: FillBlankDropdownOption[],
  points: number,
  orderIndex: number
) {
  return {
    question_type: 'FILL_BLANK_DROPDOWN',
    question_text: questionText,
    settings: settings,
    points: points,
    order_index: orderIndex,
    is_required: true,
    answer_options: options.map(opt => ({
      blank_id: opt.blank_id,
      option_text: opt.option_text,
      is_correct: opt.is_correct,
      order_index: opt.order_index,
    })),
  };
}

// ============================================
// AUTO INITIALIZATION
// ============================================

/**
 * Tự động tạo settings từ question text
 */
export function autoGenerateTextSettings(questionText: string): FillBlankTextSettings {
  const blankIds = extractBlankIds(questionText);
  
  return {
    blank_count: blankIds.length,
    blanks: blankIds.map(id => ({
      blank_id: id,
      placeholder: `Nhập đáp án cho blank ${id}`,
      label: `Chỗ trống ${id}`,
    })),
  };
}

/**
 * Tự động tạo settings từ question text
 */
export function autoGenerateDropdownSettings(questionText: string): FillBlankDropdownSettings {
  const blankIds = extractBlankIds(questionText);
  
  return {
    blank_count: blankIds.length,
    blanks: blankIds.map(id => ({
      blank_id: id,
      label: `Dropdown ${id}`,
    })),
  };
}

// ============================================
// GRADING HELPERS
// ============================================

/**
 * Check xem student answer có đúng không (client-side check)
 * Chỉ dùng cho preview, backend vẫn là source of truth
 */
export function checkFillBlankTextAnswer(
  studentAnswer: string,
  correctAnswers: FillBlankTextCorrectAnswer[]
): boolean {
  const trimmed = studentAnswer.trim();
  if (!trimmed) return false;

  return correctAnswers.some(correct => {
    let correctText = correct.answer_text;
    let studentText = trimmed;

    if (!correct.case_sensitive) {
      correctText = correctText.toLowerCase();
      studentText = studentText.toLowerCase();
    }

    if (correct.exact_match) {
      return studentText === correctText;
    } else {
      return studentText.includes(correctText);
    }
  });
}

/**
 * Get all correct answers cho một blank (for display)
 */
export function getCorrectAnswersForBlank(
  blankId: number,
  correctAnswers: FillBlankTextCorrectAnswer[]
): FillBlankTextCorrectAnswer[] {
  return correctAnswers.filter(ans => ans.blank_id === blankId);
}

/**
 * Get correct option cho một blank trong dropdown question
 */
export function getCorrectOptionForBlank(
  blankId: number,
  options: FillBlankDropdownOption[]
): FillBlankDropdownOption | undefined {
  return options.find(opt => opt.blank_id === blankId && opt.is_correct);
}

// ============================================
// EXPORT ALL
// ============================================

export const FillBlankUtils = {
  // Blank detection
  countBlanks,
  extractBlankIds,
  parseBlankPositions,
  replaceBlanksWithValues,
  
  // Validation
  validateFillBlankText,
  validateFillBlankDropdown,
  
  // Data transformation
  prepareFillBlankTextForAPI,
  prepareFillBlankDropdownForAPI,
  
  // Auto initialization
  autoGenerateTextSettings,
  autoGenerateDropdownSettings,
  
  // Grading helpers
  checkFillBlankTextAnswer,
  getCorrectAnswersForBlank,
  getCorrectOptionForBlank,
};

export default FillBlankUtils;