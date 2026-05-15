export interface ProjectCard {
  project_id: string;
  user_id?: string;
  req_session_id: string;
  project_title?: string;
  project_description?: string;
  description?: string;
  stage: string;
  created_at: string;
  updated_at: string;
}