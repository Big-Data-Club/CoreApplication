"use client";

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';

import type {
  FillBlankTextSettings,
  FillBlankTextCorrectAnswer,
  FillBlankTextEditorProps,
} from '@/fillBlankType';

/**
 * Component để teacher tạo câu hỏi FILL_BLANK_TEXT
 * 
 * Features:
 * - Auto-detect {BLANK_X} trong question text
 * - Cho phép config placeholder và label cho mỗi blank
 * - Quản lý multiple correct answers per blank
 * - Case sensitive và exact match options
 */
export default function FillBlankTextEditor({
  questionText,
  settings: initialSettings,
  correctAnswers,
  onChange,
}: FillBlankTextEditorProps) {
  const [localText, setLocalText] = useState(questionText);
  const [localAnswers, setLocalAnswers] = useState<FillBlankTextCorrectAnswer[]>(correctAnswers);
  const [settings, setSettings] = useState<FillBlankTextSettings>(
    initialSettings || { blank_count: 0, blanks: [] }
  );

  // Auto-detect blanks from question text
  useEffect(() => {
    const blankMatches = localText.match(/\{BLANK_(\d+)\}/g);
    if (blankMatches) {
      const blankIds = blankMatches
        .map(m => parseInt(m.match(/\d+/)![0]))
        .filter((id, index, self) => self.indexOf(id) === index) // Remove duplicates
        .sort((a, b) => a - b);

      const newSettings: FillBlankTextSettings = {
        blank_count: blankIds.length,
        blanks: blankIds.map(id => {
          // Preserve existing blank config if exists
          const existing = settings.blanks.find(b => b.blank_id === id);
          return existing || {
            blank_id: id,
            placeholder: `Nhập đáp án cho blank ${id}`,
            label: `Chỗ trống ${id}`,
          };
        }),
      };

      setSettings(newSettings);

      // Emit changes
      onChange(localText, newSettings, localAnswers);
    } else {
      setSettings({ blank_count: 0, blanks: [] });
      onChange(localText, { blank_count: 0, blanks: [] }, localAnswers);
    }
  }, [localText]);

  // Update blank config
  const updateBlankConfig = (blankId: number, field: 'placeholder' | 'label', value: string) => {
    const newSettings = {
      ...settings,
      blanks: settings.blanks.map(b =>
        b.blank_id === blankId ? { ...b, [field]: value } : b
      ),
    };
    setSettings(newSettings);
    onChange(localText, newSettings, localAnswers);
  };

  // Add correct answer
  const addCorrectAnswer = (blankId: number) => {
    const newAnswers = [
      ...localAnswers,
      {
        blank_id: blankId,
        answer_text: '',
        case_sensitive: false,
        exact_match: true,
      },
    ];
    setLocalAnswers(newAnswers);
    onChange(localText, settings, newAnswers);
  };

  // Update correct answer
  const updateCorrectAnswer = (
    index: number,
    field: keyof FillBlankTextCorrectAnswer,
    value: any
  ) => {
    const newAnswers = localAnswers.map((ans, i) =>
      i === index ? { ...ans, [field]: value } : ans
    );
    setLocalAnswers(newAnswers);
    onChange(localText, settings, newAnswers);
  };

  // Remove correct answer
  const removeCorrectAnswer = (index: number) => {
    const newAnswers = localAnswers.filter((_, i) => i !== index);
    setLocalAnswers(newAnswers);
    onChange(localText, settings, newAnswers);
  };

  // Get answers for a specific blank
  const getAnswersForBlank = (blankId: number) => {
    return localAnswers
      .map((ans, index) => ({ ...ans, originalIndex: index }))
      .filter(ans => ans.blank_id === blankId);
  };

  return (
    <div className="space-y-6">
      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="font-semibold text-blue-900 mb-2">💡 Hướng dẫn</h4>
        <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
          <li>Sử dụng <code className="bg-blue-100 px-1 rounded">{`{BLANK_1}`}</code>, <code className="bg-blue-100 px-1 rounded">{`{BLANK_2}`}</code>, ... trong câu hỏi</li>
          <li>Blanks sẽ tự động được phát hiện</li>
          <li>Có thể thêm nhiều đáp án đúng cho mỗi blank</li>
          <li>Học viên sẽ nhập text vào các ô trống</li>
        </ul>
      </div>

      {/* Question Text Input */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Câu hỏi với blanks *
        </label>
        <textarea
          value={localText}
          onChange={(e) => setLocalText(e.target.value)}
          className="w-full px-4 py-3 border-2 rounded-lg focus:ring-2 focus:ring-blue-500 font-mono"
          rows={4}
          placeholder="VD: The capital of {BLANK_1} is {BLANK_2}."
          required
        />
        <p className="text-xs text-gray-500 mt-1">
          {settings.blank_count > 0
            ? `✓ Đã phát hiện ${settings.blank_count} blank(s)`
            : '⚠️ Chưa có blank nào. Sử dụng {BLANK_1}, {BLANK_2}, ...'}
        </p>
      </div>

      {/* Blank Configuration */}
      {settings.blanks.length > 0 && (
        <div className="border-t pt-6">
          <h3 className="font-semibold text-lg mb-4">Cấu hình Blanks</h3>
          
          {settings.blanks.map((blank) => {
            const answersForBlank = getAnswersForBlank(blank.blank_id);
            
            return (
              <div key={blank.blank_id} className="border rounded-lg p-4 mb-4 bg-gray-50">
                <div className="flex items-center gap-2 mb-4">
                  <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-bold">
                    {`{BLANK_${blank.blank_id}}`}
                  </span>
                </div>

                {/* Blank Label & Placeholder */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div>
                    <label className="block text-xs font-medium mb-1 text-gray-700">
                      Tên hiển thị
                    </label>
                    <input
                      type="text"
                      value={blank.label || ''}
                      onChange={(e) => updateBlankConfig(blank.blank_id, 'label', e.target.value)}
                      className="w-full px-3 py-2 text-sm border rounded-lg"
                      placeholder="VD: Tên quốc gia"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1 text-gray-700">
                      Placeholder (gợi ý)
                    </label>
                    <input
                      type="text"
                      value={blank.placeholder || ''}
                      onChange={(e) => updateBlankConfig(blank.blank_id, 'placeholder', e.target.value)}
                      className="w-full px-3 py-2 text-sm border rounded-lg"
                      placeholder="VD: Nhập tên quốc gia"
                    />
                  </div>
                </div>

                {/* Correct Answers for this Blank */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm font-medium text-gray-700">
                      Đáp án đúng ({answersForBlank.length})
                    </label>
                    <Button
                      type="button"
                      onClick={() => addCorrectAnswer(blank.blank_id)}
                      variant="outline"
                      className="text-xs px-3 py-1"
                    >
                      + Thêm đáp án
                    </Button>
                  </div>

                  {answersForBlank.length === 0 ? (
                    <div className="text-center py-4 bg-red-50 border border-red-200 rounded-lg">
                      <p className="text-sm text-red-600">
                        ⚠️ Chưa có đáp án đúng cho blank này
                      </p>
                      <Button
                        type="button"
                        onClick={() => addCorrectAnswer(blank.blank_id)}
                        variant="outline"
                        className="mt-2 text-xs"
                      >
                        + Thêm đáp án đầu tiên
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {answersForBlank.map((answer) => (
                        <div
                          key={answer.originalIndex}
                          className="bg-white border rounded-lg p-3 space-y-2"
                        >
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={answer.answer_text}
                              onChange={(e) =>
                                updateCorrectAnswer(
                                  answer.originalIndex,
                                  'answer_text',
                                  e.target.value
                                )
                              }
                              className="flex-1 px-3 py-2 text-sm border rounded-lg"
                              placeholder="Đáp án đúng..."
                              required
                            />
                            <Button
                              type="button"
                              onClick={() => removeCorrectAnswer(answer.originalIndex)}
                              variant="outline"
                              className="px-3 py-2 text-red-600 hover:bg-red-50"
                            >
                              ✕
                            </Button>
                          </div>

                          <div className="flex gap-4 text-xs">
                            <label className="flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={answer.case_sensitive}
                                onChange={(e) =>
                                  updateCorrectAnswer(
                                    answer.originalIndex,
                                    'case_sensitive',
                                    e.target.checked
                                  )
                                }
                                className="mr-2"
                              />
                              Phân biệt HOA/thường
                            </label>
                            <label className="flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={answer.exact_match}
                                onChange={(e) =>
                                  updateCorrectAnswer(
                                    answer.originalIndex,
                                    'exact_match',
                                    e.target.checked
                                  )
                                }
                                className="mr-2"
                              />
                              Khớp chính xác
                            </label>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Validation Summary */}
      {settings.blanks.length > 0 && (
        <div className="bg-gray-50 border rounded-lg p-4">
          <h4 className="font-semibold text-sm mb-2">📊 Tổng quan</h4>
          <ul className="text-sm space-y-1">
            <li>• Tổng số blanks: <strong>{settings.blank_count}</strong></li>
            <li>• Tổng số đáp án: <strong>{localAnswers.length}</strong></li>
            {settings.blanks.map(blank => {
              const count = localAnswers.filter(a => a.blank_id === blank.blank_id).length;
              return (
                <li key={blank.blank_id} className={count === 0 ? 'text-red-600' : 'text-green-600'}>
                  • {`{BLANK_${blank.blank_id}}`}: <strong>{count}</strong> đáp án
                  {count === 0 && ' ⚠️'}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}