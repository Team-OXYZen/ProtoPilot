export type InputType =
  | 'text'
  | 'textarea'
  | 'single-select'
  | 'multi-select'
  | 'number';

export interface Question {
  summary: string;
  question: string;
  suggestions?: any[];
  project_name?: string;
  spec?: {};
}

export interface Response {
  session_id: string;
  reply: string;
  done: boolean;
  spec: Question
}