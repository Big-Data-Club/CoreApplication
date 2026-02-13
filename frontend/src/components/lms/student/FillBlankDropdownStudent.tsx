"use client";

import { useState, useEffect } from 'react';
import type {
  FillBlankDropdownSettings,
  FillBlankDropdownOption,
  FillBlankDropdownStudentAnswer,
  FillBlankDropdownStudentProps,
} from '@/fillBlankType';

/**
 * Component for students to answer FILL_BLANK_DROPDOWN questions
 * 
 * Features:
 * - Displays question with dropdown selects for blanks
 * - Supports both quiz-taking and review modes
 * - Shows correct answers in review mode (if enabled)
 * - Highlights correct/incorrect selections
 * - Preserves student answers
 */
export default function FillBlankDropdownStudent({
  questionText,
  settings,
  options,
  value,
  onChange,
  disabled = false,
  showCorrectAnswers = false,
  studentAnswer,
}: FillBlankDropdownStudentProps) {
  const [localValue, setLocalValue] = useState<FillBlankDropdownStudentAnswer>(
    value || { blanks: [] }
  );

  // Sync with external value changes
  useEffect(() => {
    setLocalValue(value || { blanks: [] });
  }, [value]);

  // Parse question text to get blank positions
  const parseQuestionText = (): Array<{ type: 'text' | 'blank'; content: string; blankId?: number }> => {
    const parts: Array<{ type: 'text' | 'blank'; content: string; blankId?: number }> = [];
    const regex = /\{BLANK_(\d+)\}/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(questionText)) !== null) {
      // Add text before blank
      if (match.index > lastIndex) {
        parts.push({
          type: 'text',
          content: questionText.substring(lastIndex, match.index),
        });
      }

      // Add blank
      const blankId = parseInt(match[1]);
      parts.push({
        type: 'blank',
        content: match[0],
        blankId,
      });

      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < questionText.length) {
      parts.push({
        type: 'text',
        content: questionText.substring(lastIndex),
      });
    }

    return parts;
  };

  // Get student selected option for a blank
  const getBlankSelection = (blankId: number): number | null => {
    const blank = localValue.blanks.find(b => b.blank_id === blankId);
    return blank?.selected_option_id || null;
  };

  // Update student selection for a blank
  const updateBlankSelection = (blankId: number, optionId: number) => {
    const newBlanks = localValue.blanks.filter(b => b.blank_id !== blankId);
    newBlanks.push({ blank_id: blankId, selected_option_id: optionId });

    const newValue = { blanks: newBlanks };
    setLocalValue(newValue);
    onChange(newValue);
  };

  // Get options for a specific blank
  const getOptionsForBlank = (blankId: number): FillBlankDropdownOption[] => {
    return options
      .filter(opt => opt.blank_id === blankId)
      .sort((a, b) => a.order_index - b.order_index);
  };

  // Get blank config
  const getBlankConfig = (blankId: number) => {
    return settings.blanks.find(b => b.blank_id === blankId);
  };

  // Check if student selection is correct (for review mode)
  const isSelectionCorrect = (blankId: number): boolean | null => {
    if (!showCorrectAnswers) return null;

    const selectedOptionId = getBlankSelection(blankId);
    if (!selectedOptionId) return false;

    const selectedOption = options.find(opt => opt.id === selectedOptionId);
    if (!selectedOption) return null;

    return selectedOption.is_correct;
  };

  // Get correct option for a blank (for review mode)
  const getCorrectOption = (blankId: number): FillBlankDropdownOption | null => {
    if (!showCorrectAnswers) return null;
    
    const correctOption = options.find(
      opt => opt.blank_id === blankId && opt.is_correct
    );
    return correctOption || null;
  };

  const parts = parseQuestionText();

  return (
    <div className="space-y-4">
      {/* Question Text with Dropdowns */}
      <div className="text-lg leading-relaxed">
        {parts.map((part, index) => {
          if (part.type === 'text') {
            return <span key={index}>{part.content}</span>;
          }

          // Render blank dropdown
          const blankId = part.blankId!;
          const config = getBlankConfig(blankId);
          const blankOptions = getOptionsForBlank(blankId);
          const selectedOptionId = getBlankSelection(blankId);
          const isCorrect = isSelectionCorrect(blankId);

          return (
            <span key={index} className="inline-block mx-1">
              {/* Dropdown Select */}
              <select
                value={selectedOptionId || ''}
                onChange={(e) => updateBlankSelection(blankId, parseInt(e.target.value))}
                disabled={disabled}
                className={`
                  inline-block px-3 py-1 border-2 rounded-lg
                  transition-all duration-200
                  min-w-[150px] max-w-[300px]
                  cursor-pointer
                  ${disabled ? 'bg-gray-50 cursor-not-allowed' : 'bg-white'}
                  ${
                    isCorrect === null
                      ? 'border-blue-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-200'
                      : isCorrect
                      ? 'border-green-500 bg-green-50'
                      : 'border-red-500 bg-red-50'
                  }
                `}
              >
                <option value="">-- Chọn --</option>
                {blankOptions.map(opt => (
                  <option key={opt.id} value={opt.id}>
                    {opt.option_text}
                  </option>
                ))}
              </select>
              
              {/* Review Mode: Show indicator */}
              {disabled && isCorrect !== null && (
                <span className="ml-2 inline-flex items-center">
                  {isCorrect ? (
                    <span className="text-green-600 font-bold text-xl">✓</span>
                  ) : (
                    <span className="text-red-600 font-bold text-xl">✗</span>
                  )}
                </span>
              )}
            </span>
          );
        })}
      </div>

      {/* Review Mode: Show detailed feedback */}
      {showCorrectAnswers && settings.blanks.length > 0 && (
        <div className="mt-6 space-y-3">
          <h4 className="font-semibold text-gray-800 text-sm">Đáp án:</h4>
          
          {settings.blanks.map((blank) => {
            const selectedOptionId = getBlankSelection(blank.blank_id);
            const selectedOption = options.find(opt => opt.id === selectedOptionId);
            const correctOption = getCorrectOption(blank.blank_id);
            const isCorrect = isSelectionCorrect(blank.blank_id);

            return (
              <div
                key={blank.blank_id}
                className={`p-3 rounded-lg border-2 ${
                  isCorrect
                    ? 'bg-green-50 border-green-200'
                    : 'bg-red-50 border-red-200'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0">
                    <span className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs font-bold">
                      BLANK_{blank.blank_id}
                    </span>
                  </div>
                  
                  <div className="flex-1 space-y-2">
                    {/* Student Selection */}
                    <div>
                      <p className="text-xs text-gray-600 font-medium mb-1">Lựa chọn của bạn:</p>
                      <p className={`font-medium ${
                        isCorrect ? 'text-green-700' : 'text-red-700'
                      }`}>
                        {selectedOption ? (
                          selectedOption.option_text
                        ) : (
                          <span className="italic text-gray-400">Chưa chọn</span>
                        )}
                      </p>
                    </div>

                    {/* Correct Answer */}
                    {!isCorrect && correctOption && (
                      <div>
                        <p className="text-xs text-gray-600 font-medium mb-1">Đáp án đúng:</p>
                        <p className="text-green-700 font-medium">
                          • {correctOption.option_text}
                        </p>
                      </div>
                    )}

                    {/* Label */}
                    {blank.label && (
                      <p className="text-xs text-gray-500 italic mt-1">
                        {blank.label}
                      </p>
                    )}
                  </div>

                  <div className="flex-shrink-0">
                    {isCorrect ? (
                      <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                        <span className="text-white font-bold text-lg">✓</span>
                      </div>
                    ) : (
                      <div className="w-8 h-8 bg-red-500 rounded-full flex items-center justify-center">
                        <span className="text-white font-bold text-lg">✗</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Quiz Taking Mode: Show all available options */}
      {!disabled && !showCorrectAnswers && (
        <div className="mt-4 bg-purple-50 border border-purple-200 rounded-lg p-3">
          <p className="text-sm text-purple-800">
            <strong>💡 Gợi ý:</strong> Chọn đáp án phù hợp từ các dropdown trên câu
          </p>
          {settings.blanks.length > 0 && (
            <div className="mt-2 space-y-2">
              {settings.blanks.map(blank => {
                const blankOptions = getOptionsForBlank(blank.blank_id);
                return (
                  <div key={blank.blank_id} className="text-xs">
                    <strong className="text-purple-700">BLANK_{blank.blank_id}</strong>
                    {blank.label && <span className="text-gray-600"> ({blank.label})</span>}
                    <span className="text-gray-600"> - {blankOptions.length} lựa chọn</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}