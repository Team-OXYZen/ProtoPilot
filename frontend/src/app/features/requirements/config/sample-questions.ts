import { Question } from '../models/response.model';

export const REQUIREMENTS_QUESTION_FLOW: Question[] = [
  // {
  //   id: 'project_name',
  //   label: 'What is the name of your project?',
  //   inputType: 'text',
  // },
  // {
  //   id: 'problem_statement',
  //   label: 'What problem are you trying to solve?',
  //   inputType: 'text',
  // },
  // {
  //   id: 'target_users',
  //   label: 'Who are your target users?',
  //   inputType: 'multi-select',
  //   suggestions: [{label: 'Admins', selected: false}, {label: 'End Users', selected: false}, {label: 'Managers', selected: false}],
  // }
];

export enum CONSTANTS {
  REQUIREMENTS_AGENT_NAME = "requirements",
  REQUIREMENTS_AGENT_URL = "https://agent-backend-868822018920.us-central1.run.app/chat",
  REQUIREMENTS_INITIAL_PROMPT = "Hi, What are you trying to build today?",
  REQUIREMENTS_DONE_TEXT = "Great! I think we have enough clarity on the idea now!",
  THINKING_TEXT = "Thinking...",
  REQUIREMENTS_DONE_SUBTEXT = "Here are the requirements we discussed in a structured format:",
  ERROR_TEXT = "Something went wrong. Please try again! "
}