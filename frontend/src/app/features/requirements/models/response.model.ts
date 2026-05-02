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
  message?: string;
}

export interface Spec {
  project_name: string;
  problem_statement: string;
  target_users: string[];
  goals: string[];
  non_goals: string[];
  functional_requirements: string[];
  non_functional_requirements: {
    "performance": string;
    "security": string;
    "scalability": string;
    "availability": string
  };
  core_entities: string[];
  assumptions: string[];
  constraints: string[];
  open_questions: string[]
}

export interface Response {
  session_id: string;
  project_id: string;
  stage: string;
  reply: Question;
  spec: Spec;
  nontech_artifacts_md: Record<string, string>;
  technical_artifacts_md: Record<string, string>;
  artifacts_md: Record<string, string>;
}

export interface WizardCompleteData {
  spec: Spec;
  nontech_artifacts_md: Record<string, string>;
  technical_artifacts_md: Record<string, string>;
}