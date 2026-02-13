export interface FillBlankTextSettings {
  blank_count: number;
  
  blanks: Array<{
    blank_id: number;
    placeholder?: string;
    label?: string;
  }>;
}

export interface FillBlankTextCorrectAnswer {
  blank_id: number;
  answer_text: string;
  case_sensitive: boolean;
  exact_match: boolean;
  blank_position?: number;
}

export interface FillBlankDropdownSettings {
  blank_count: number;
  
  blanks: Array<{
    blank_id: number;
    label?: string;
  }>;
}

export interface FillBlankDropdownOption {
  id?: number;
  blank_id: number;
  option_text: string;
  is_correct: boolean;
  order_index: number;
}

export interface FillBlankTextStudentAnswer {
  blanks: Array<{
    blank_id: number;
    answer: string;
  }>;
}

export interface FillBlankDropdownStudentAnswer {
  blanks: Array<{
    blank_id: number;
    selected_option_id: number;
  }>;
}

export interface FillBlankTextEditorProps {
  questionText: string;
  settings: FillBlankTextSettings;
  correctAnswers: FillBlankTextCorrectAnswer[];
  onChange: (
    questionText: string,
    settings: FillBlankTextSettings,
    correctAnswers: FillBlankTextCorrectAnswer[]
  ) => void;
}

export interface FillBlankDropdownEditorProps {
  questionText: string;
  settings: FillBlankDropdownSettings;
  options: FillBlankDropdownOption[];
  onChange: (
    questionText: string,
    settings: FillBlankDropdownSettings,
    options: FillBlankDropdownOption[]
  ) => void;
}

export interface FillBlankTextStudentProps {
  questionText: string;
  settings: FillBlankTextSettings;
  value: FillBlankTextStudentAnswer;
  onChange: (answer: FillBlankTextStudentAnswer) => void;
  disabled?: boolean;
  showCorrectAnswers?: boolean;
  correctAnswers?: FillBlankTextCorrectAnswer[];
}

export interface FillBlankDropdownStudentProps {
  questionText: string;
  settings: FillBlankDropdownSettings;
  options: FillBlankDropdownOption[];
  value: FillBlankDropdownStudentAnswer;
  onChange: (answer: FillBlankDropdownStudentAnswer) => void;
  disabled?: boolean;
  showCorrectAnswers?: boolean;
  studentAnswer?: FillBlankDropdownStudentAnswer;
}

export interface BlankPosition {
  blank_id: number;
  start_index: number;
  end_index: number;
  placeholder: string;
}

export interface FillBlankValidationError {
  field: string;
  message: string;
  blank_id?: number;
}