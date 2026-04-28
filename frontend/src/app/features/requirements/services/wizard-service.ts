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

  startSession = ():void => {
    let session: Session = {
      id : crypto.randomUUID(),
    }
    let project: Project = {
      id: crypto.randomUUID(),
    }
    this.sessionSubject.next(session);
    this.projectSubject.next(project);
  }

  sendMessage = (message: string):Observable<Response|null> => {
    if (!this.session) return of(null);
    
    return this.http.post<Response>(CONSTANTS.REQUIREMENTS_AGENT_URL, {
        // session_id: this.session?.id,
        // project_id: this.project?.id,
        session_id: "todo",
        project_id: "todo",
        message: message
      });
  }
  
}
