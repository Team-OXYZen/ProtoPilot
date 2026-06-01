import { inject, Injectable } from '@angular/core';
import { BehaviorSubject, delay, map, Observable, of } from 'rxjs';
import { Session } from '../models/session.model';
import { Question, Response } from '../models/response.model';
import { CONSTANTS, REQUIREMENTS_QUESTION_FLOW } from '../config/sample-questions';
import { HttpClient } from '@angular/common/http';
import { Project } from '../models/project.model';
import { AuthService } from '../../../core/auth.service';
import { environment } from '../../../../environments/environment';

@Injectable({
  providedIn: 'root',
})
export class WizardService {

  userId = '';
  projectTitle = '';
  projectDescription = '';

  http = inject(HttpClient);
  private authService = inject(AuthService);
  private readonly apiBaseUrl = environment.apiBaseUrl;

  private sessionSubject:BehaviorSubject<Session | null> = new BehaviorSubject<Session | null>(null);
  session$ = this.sessionSubject.asObservable();

  get session():Session|null {
    return this.sessionSubject.value;
  }

  private projectSubject:BehaviorSubject<Project | null> = new BehaviorSubject<Project | null>(null);
  project$ = this.projectSubject.asObservable();


  get project():Project|null {
    return this.projectSubject.value;
  }

  startSession = (): void => {
    if (this.session && this.project) {
      return;
    }
    this.sessionSubject.next({ id: crypto.randomUUID() });
    this.projectSubject.next({ id: crypto.randomUUID() });
  }

  resetSession = (): void => {
    this.sessionSubject.next({ id: crypto.randomUUID() });
    this.projectSubject.next({ id: crypto.randomUUID() });
    this.projectTitle = '';
    this.projectDescription = '';
  }


  createProject(userId: string, title: string, description: string): void {
    this.userId = userId;
    this.projectTitle = title;
    this.projectDescription = description;

    this.sessionSubject.next({
      id: crypto.randomUUID(),
    });

    this.projectSubject.next({
      id: crypto.randomUUID(),
    });

  }

  createProjectInDb(): Observable<any> {
    return this.http.post<any>(`${this.apiBaseUrl}/projects`, {
      user_id: this.userId,
      project_id: this.project?.id,
      session_id: this.session?.id,
      project_title: this.projectTitle,
      project_description: this.projectDescription,
    });
  }

  sendMessage = (message: string, saveToHistory: boolean = true): Observable<Response | null> => {
    if (!this.session || !this.project) return of(null);

    return this.http.post<Response>(CONSTANTS.REQUIREMENTS_AGENT_URL, {
      user_id: this.userId,
      project_id: this.project.id,
      session_id: this.session.id,
      project_title: this.projectTitle,
      project_description: this.projectDescription,
      message,
      save_to_history: saveToHistory,
    });
  }

  getProjects(): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/projects`, {
      params: { user_id: this.requestUserId },
    });
  }

  getProject(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/projects/${projectId}`, {
      params: { user_id: this.requestUserId },
    });
  }

  getProjectMessages(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/projects/${projectId}/messages`, {
      params: { user_id: this.requestUserId },
    });
  }

  logProjectActivity(projectId: string, message: string, status: 'info' | 'running' | 'success' | 'error' = 'info'): Observable<any> {
    return this.http.post<any>(`${this.apiBaseUrl}/projects/${projectId}/messages/activity`, {
      session_id: this.session?.id,
      message,
      status,
    });
  }

  deployProject(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.apiBaseUrl}/projects/${projectId}/deploy`, {});
  }

  getDeployStatus(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/projects/${projectId}/deploy/status`);
  }

  undeployProject(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.apiBaseUrl}/projects/${projectId}/undeploy`, {});
  }

  getGitHubConnectionStatus(): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/integrations/github/oauth/status`);
  }

  startGitHubOAuth(): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/integrations/github/oauth/start`);
  }

  exportGeneratedCodeToGithub(projectId: string, sessionId: string, owner: string, repo: string): Observable<any> {
    return this.http.post<any>(`${this.apiBaseUrl}/integrations/github/export`, {
      project_id: projectId,
      session_id: sessionId,
      owner,
      repo,
      base_branch: 'main',
    });
  }

  createJiraTasks(projectId: string, sessionId: string): Observable<any> {
    return this.http.post<any>(`${this.apiBaseUrl}/integrations/jira/create-tasks`, {
      project_id: projectId,
      session_id: sessionId,
    });
  }

  exportArtifactsToConfluence(projectId: string, sessionId: string, confluenceSpaceKey: string): Observable<any> {
    return this.http.post<any>(`${this.apiBaseUrl}/integrations/confluence/export-artifacts`, {
      project_id: projectId,
      session_id: sessionId,
      confluence_space_key: confluenceSpaceKey,
    });
  }

  getUserPreferences(): Observable<{ preferences: Record<string, string> }> {
    return this.http.get<{ preferences: Record<string, string> }>(`${this.apiBaseUrl}/preferences`);
  }

  saveUserPreferences(preferences: Record<string, string>): Observable<{ preferences: Record<string, string> }> {
    return this.http.put<{ preferences: Record<string, string> }>(`${this.apiBaseUrl}/preferences`, {
      preferences,
    });
  }

  deleteProject(projectId: string): Observable<any> {
    return this.http.delete<any>(`${this.apiBaseUrl}/projects/${projectId}`);
  }

  updateProject(projectId: string, title: string, description: string): Observable<any> {
    return this.http.patch<any>(`${this.apiBaseUrl}/projects/${projectId}`, {
      project_title: title,
      project_description: description,
    });
  }

  loadExistingProject(project: any): void {
    this.userId = this.authService.getCurrentUser()()?.username || '';

    this.sessionSubject.next({
      id: project.session_id || project.req_session_id || crypto.randomUUID(),
    });

    this.projectSubject.next({
      id: project.project_id,
      title: project.project_title,
    });

    console.log('Loaded existing project:', project.project_id);
  }

  private get requestUserId(): string {
    return this.authService.getCurrentUser()()?.username || this.userId;
  }
}
