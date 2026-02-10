import React, { useState } from 'react';

// Component cho câu hỏi một lựa chọn (Radio)
export const SingleChoiceQuestion = ({ question, value, onChange, error }) => {
  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
      </div>
      <div className="space-y-3">
        {question.options.map((option, idx) => (
          <label
            key={idx}
            className="flex items-center gap-3 cursor-pointer hover:bg-white/50 p-2 border border-transparent hover:border-[#5a4a3a] transition-colors"
          >
            <input
              type="radio"
              name={question.id}
              value={option}
              checked={value === option}
              onChange={(e) => onChange(question.id, e.target.value)}
              className="w-4 h-4 accent-[#2c2416]"
            />
            <span className="text-[#2c2416]">{option}</span>
          </label>
        ))}
      </div>
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi nhiều lựa chọn (Checkbox)
export const MultipleChoiceQuestion = ({ question, value = [], onChange, error }
  : { question: any, value?: any[], onChange: any, error?: any }
) => {
  const handleCheckboxChange = (option: any) => {
    const newValue = value.includes(option)
      ? value.filter(v => v !== option)
      : [...value, option];
    
    if (question.constraints?.minChoices && newValue.length < question.constraints.minChoices && newValue.length > 0) {
      onChange(question.id, newValue);
      return;
    }
    if (question.constraints?.maxChoices && newValue.length > question.constraints.maxChoices) {
      return;
    }
    
    onChange(question.id, newValue);
  };

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
        {question.constraints && (
          <p className="text-xs text-[#5a4a3a] mt-1">
            {question.constraints.minChoices && `Tối thiểu: ${question.constraints.minChoices} lựa chọn. `}
            {question.constraints.maxChoices && `Tối đa: ${question.constraints.maxChoices} lựa chọn.`}
          </p>
        )}
      </div>
      <div className="space-y-3">
        {question.options.map((option, idx) => (
          <label
            key={idx}
            className="flex items-center gap-3 cursor-pointer hover:bg-white/50 p-2 border border-transparent hover:border-[#5a4a3a] transition-colors"
          >
            <input
              type="checkbox"
              checked={value.includes(option)}
              onChange={() => handleCheckboxChange(option)}
              className="w-4 h-4 accent-[#2c2416]"
            />
            <span className="text-[#2c2416]">{option}</span>
          </label>
        ))}
      </div>
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi trả lời ngắn
export const ShortAnswerQuestion = ({ question, value = '', onChange, error }) => {
  const handleChange = (e) => {
    const newValue = e.target.value;
    if (question.constraints?.maxLength && newValue.length > question.constraints.maxLength) {
      return;
    }
    onChange(question.id, newValue);
  };

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
        {question.constraints?.maxLength && (
          <p className="text-xs text-[#5a4a3a] mt-1">
            {value.length}/{question.constraints.maxLength} ký tự
          </p>
        )}
      </div>
      <input
        type="text"
        value={value}
        onChange={handleChange}
        placeholder={question.placeholder || "Nhập câu trả lời của bạn..."}
        className="w-full border-b-2 border-[#2c2416] bg-white/40 backdrop-blur-sm p-2 text-[#2c2416] placeholder-[#5a4a3a] focus:outline-none focus:border-[#5a4a3a]"
      />
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi trả lời dài
export const LongAnswerQuestion = ({ question, value = '', onChange, error }) => {
  const handleChange = (e) => {
    const newValue = e.target.value;
    if (question.constraints?.maxLength && newValue.length > question.constraints.maxLength) {
      return;
    }
    onChange(question.id, newValue);
  };

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
        {question.constraints?.maxLength && (
          <p className="text-xs text-[#5a4a3a] mt-1">
            {value.length}/{question.constraints.maxLength} ký tự
          </p>
        )}
      </div>
      <textarea
        value={value}
        onChange={handleChange}
        placeholder={question.placeholder || "Nhập câu trả lời của bạn..."}
        rows={6}
        className="w-full border-2 border-[#2c2416] backdrop-blur-sm bg-white/40 p-3 text-[#2c2416] placeholder-[#5a4a3a] focus:outline-none focus:border-[#5a4a3a] resize-none"
      />
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi số
export const NumberQuestion = ({ question, value = '', onChange, error }) => {
  const handleChange = (e) => {
    const newValue = e.target.value;
    if (newValue === '') {
      onChange(question.id, '');
      return;
    }
    
    const num = parseFloat(newValue);
    if (isNaN(num)) return;
    
    if (question.constraints?.min !== undefined && num < question.constraints.min) return;
    if (question.constraints?.max !== undefined && num > question.constraints.max) return;
    
    onChange(question.id, newValue);
  };

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
        {question.constraints && (
          <p className="text-xs text-[#5a4a3a] mt-1">
            {question.constraints.min !== undefined && `Tối thiểu: ${question.constraints.min}. `}
            {question.constraints.max !== undefined && `Tối đa: ${question.constraints.max}.`}
          </p>
        )}
      </div>
      <input
        type="number"
        value={value}
        onChange={handleChange}
        placeholder={question.placeholder || "Nhập số..."}
        min={question.constraints?.min}
        max={question.constraints?.max}
        step={question.constraints?.step || 1}
        className="w-full border-b-2 border-[#2c2416] backdrop-blur-sm bg-white/40 p-2 text-[#2c2416] placeholder-[#5a4a3a] focus:outline-none focus:border-[#5a4a3a]"
      />
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi điền vào chỗ trống
export const FillInTheBlankQuestion = ({ question, value = {}, onChange, error }) => {
  const handleBlankChange = (blankId, newValue) => {
    onChange(question.id, { ...value, [blankId]: newValue });
  };

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
      </div>
      <div className="space-y-4">
        {question.blanks.map((blank, idx) => (
          <div key={idx}>
            <label className="text-sm text-[#2c2416] mb-2 block">
              {blank.label}
            </label>
            <input
              type="text"
              value={value[blank.id] || ''}
              onChange={(e) => handleBlankChange(blank.id, e.target.value)}
              placeholder={blank.placeholder || "Điền vào đây..."}
              className="w-full border-b-2 border-[#2c2416] backdrop-blur-sm bg-white/40 p-2 text-[#2c2416] placeholder-[#5a4a3a] focus:outline-none focus:border-[#5a4a3a]"
            />
          </div>
        ))}
      </div>
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi code
export const CodeQuestion = ({ question, value = '', onChange, error }) => {
  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
        {question.language && (
          <p className="text-xs text-[#5a4a3a] mt-1">Ngôn ngữ: {question.language}</p>
        )}
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(question.id, e.target.value)}
        placeholder={question.placeholder || "// Nhập code của bạn..."}
        rows={10}
        className="w-full border-2 border-[#2c2416] backdrop-blur-sm bg-white/50 p-3 text-[#2c2416] placeholder-[#5a4a3a] focus:outline-none focus:border-[#5a4a3a] resize-none font-mono text-sm"
        style={{ fontFamily: 'monospace' }}
      />
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi phân loại/matching
export const MatchingQuestion = ({ question, value = {}, onChange, error }) => {
  const handleMatch = (itemId, category) => {
    onChange(question.id, { ...value, [itemId]: category });
  };

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
      </div>
      <div className="space-y-4">
        {question.items.map((item, idx) => (
          <div key={idx} className="border border-[#5a4a3a] p-3 backdrop-blur-sm bg-white/20">
            <p className="text-[#2c2416] mb-2 font-semibold">{item.text}</p>
            <select
              value={value[item.id] || ''}
              onChange={(e) => handleMatch(item.id, e.target.value)}
              className="w-full border-b-2 border-[#2c2416] backdrop-blur-sm bg-white/40 p-2 text-[#2c2416] focus:outline-none focus:border-[#5a4a3a]"
            >
              <option value="">-- Chọn danh mục --</option>
              {question.categories.map((cat, catIdx) => (
                <option key={catIdx} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi rating/scale
export const RatingQuestion = ({ question, value = '', onChange, error }) => {
  const scale = question.scale || { min: 1, max: 5 };
  const options:number[] = [];
  for (let i = scale.min; i <= scale.max; i++) {
    options.push(i);
  }

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
      </div>
      <div className="flex justify-between items-center gap-2">
        {scale.minLabel && (
          <span className="text-xs text-[#5a4a3a] w-20">{scale.minLabel}</span>
        )}
        <div className="flex gap-4 flex-1 justify-center">
          {options.map((opt) => (
            <label
              key={opt}
              className="flex flex-col items-center gap-2 cursor-pointer"
            >
              <input
                type="radio"
                name={question.id}
                value={opt}
                checked={value === opt.toString()}
                onChange={(e) => onChange(question.id, e.target.value)}
                className="w-5 h-5 accent-[#2c2416]"
              />
              <span className="text-sm font-bold text-[#2c2416]">{opt}</span>
            </label>
          ))}
        </div>
        {scale.maxLabel && (
          <span className="text-xs text-[#5a4a3a] w-20 text-right">{scale.maxLabel}</span>
        )}
      </div>
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi date/time
export const DateTimeQuestion = ({ question, value = '', onChange, error }) => {
  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
      </div>
      <input
        type={question.dateType || 'date'}
        value={value}
        onChange={(e) => onChange(question.id, e.target.value)}
        min={question.constraints?.min}
        max={question.constraints?.max}
        className="w-full border-2 border-[#2c2416] backdrop-blur-sm bg-white/40 p-2 text-[#2c2416] focus:outline-none focus:border-[#5a4a3a]"
      />
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

// Component cho câu hỏi Email
export const EmailQuestion = ({ question, value = '', onChange, error }) => {
  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
      </div>
      <input
        type="email"
        value={value}
        onChange={(e) => onChange(question.id, e.target.value)}
        placeholder={question.placeholder || "example@email.com"}
        className="w-full border-b-2 border-[#2c2416] backdrop-blur-sm bg-white/40 p-2 text-[#2c2416] placeholder-[#5a4a3a] focus:outline-none focus:border-[#5a4a3a]"
      />
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};

export const MatrixQuestion = ({ question, value = {}, onChange, error }) => {
  const handleChange = (rowId, columnValue) => {
    onChange(question.id, { ...value, [rowId]: columnValue });
  };

  const rows = question.rows || [];
  const columns = question.columns || [];

  return (
    <div className="border-2 border-[#2c2416] backdrop-blur-md bg-white/30 p-6 mb-6">
      <div className="mb-4">
        <label className="text-lg font-bold text-[#2c2416] flex items-center gap-2">
          {question.question}
          {question.required && <span className="text-red-600">*</span>}
        </label>
        {question.note && (
          <p className="text-sm text-[#5a4a3a] italic mt-1">{question.note}</p>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="border-2 border-[#2c2416] backdrop-blur-sm bg-white/50 p-3 text-left font-semibold text-[#2c2416] min-w-[200px]">
                {question.rowLabel || 'Tình huống sử dụng'}
              </th>
              {columns.map((col, idx) => (
                <th 
                  key={idx} 
                  className="border-2 border-[#2c2416] backdrop-blur-sm bg-white/50 p-3 text-center font-semibold text-[#2c2416] min-w-[60px]"
                >
                  {col.label || col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => (
              <tr key={rowIdx} className="hover:bg-white/40 transition-colors">
                <td className="border-2 border-[#2c2416] p-3 text-[#2c2416]">
                  {row.text || row}
                </td>
                {columns.map((col, colIdx) => {
                  const colValue = col.value || col;
                  const rowId = row.id || `row_${rowIdx}`;
                  const isChecked = value[rowId] === colValue;
                  
                  return (
                    <td 
                      key={colIdx} 
                      className="border-2 border-[#2c2416] p-3 text-center"
                    >
                      <label className="flex justify-center cursor-pointer">
                        <input
                          type="radio"
                          name={`${question.id}_${rowId}`}
                          value={colValue}
                          checked={isChecked}
                          onChange={() => handleChange(rowId, colValue)}
                          className="w-5 h-5 accent-[#2c2416] cursor-pointer"
                        />
                      </label>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {question.showBottomLabels && (
        <div className="flex justify-end gap-4 mt-2 text-xs text-[#5a4a3a] italic">
          {columns.map((col, idx) => (
            <div key={idx} className="min-w-[60px] text-center">
              {col.description}
            </div>
          ))}
        </div>
      )}

      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
    </div>
  );
};