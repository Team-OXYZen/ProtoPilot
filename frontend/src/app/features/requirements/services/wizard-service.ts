import { inject, Injectable } from '@angular/core';
import { BehaviorSubject, delay, map, Observable, of } from 'rxjs';
import { Session } from '../models/session.model';
import { Question, Response } from '../models/response.model';
import { CONSTANTS, REQUIREMENTS_QUESTION_FLOW } from '../config/sample-questions';
import { HttpClient } from '@angular/common/http';
import { Project } from '../models/project.model';

@Injectable({
  providedIn: 'root',
})
export class WizardService {

  http = inject(HttpClient);

  private sessionSubject:BehaviorSubject<Session | null> = new BehaviorSubject<Session | null>(null);
  session$ = this.sessionSubject.asObservable();
  
  get session():Session|null {
    return this.sessionSubject.value;
  }
  
  private projectSubject:BehaviorSubject<Session | null> = new BehaviorSubject<Session | null>(null);
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
  }

  sendMessage = (message: string, saveToHistory: boolean = true): Observable<Response | null> => {
    if (!this.session) return of(null);
    
    return this.http.post<Response>(CONSTANTS.REQUIREMENTS_AGENT_URL, {
      session_id: this.session?.id,
      project_id: this.project?.id,
      message: message,
      save_to_history: saveToHistory
    });
  }

  getProjects(): Observable<any> {
  return this.http.get<any>('https://protopilot-api-868822018920.us-west2.run.app/projects');
  }

  getProject(projectId: string): Observable<any> {
    return this.http.get<any>(`https://protopilot-api-868822018920.us-west2.run.app/projects/${projectId}`);
  }

  getProjectMessages(projectId: string): Observable<any> {
    return this.http.get<any>(`https://protopilot-api-868822018920.us-west2.run.app/projects/${projectId}/messages`);
  }

  loadExistingProject(project: any): void {
    this.sessionSubject.next({
      id: project.session_id || project.req_session_id || crypto.randomUUID(),
    });

    this.projectSubject.next({
      id: project.project_id,
    });

    console.log('Loaded existing project:', project.project_id);
  }
  
}
