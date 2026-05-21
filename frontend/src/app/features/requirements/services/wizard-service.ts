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
  private baseUrl = environment.apiUrl;

  http = inject(HttpClient);
  private authService = inject(AuthService);

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
    return this.http.post<any>(`${this.baseUrl}/projects`, {
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
  return this.http.get<any>(`${this.baseUrl}/projects`);
  }

  getProject(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}`);
  }

  getProjectMessages(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/messages`);
  }

  deployProject(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/deploy`, {});
  }

  getDeployStatus(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/deploy/status`);
  }

  undeployProject(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/undeploy`, {});
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




  
}
