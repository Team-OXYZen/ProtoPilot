import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { WizardService } from '../../services/wizard-service';
import { SpecService } from '../../../spec-review/services/spec.service';
import { Question, Response } from '../../models/response.model';
import { CONSTANTS } from '../../config/sample-questions';
import { catchError, EMPTY, map } from 'rxjs';
import { HeaderComponent } from '../../../../shared/components/header/header.component';
import { LoaderService } from '../../../../shared/services/loader.service';

const FRIENDLY_WIZARD_ERROR = 'Sorry, something went wrong while preparing the next step. Please try again in a moment.';

@Component({
  selector: 'app-wizard',
  templateUrl: './wizard.html',
  styleUrls: ['./wizard.scss'],
  standalone: true,
  imports: [FormsModule, HeaderComponent]
})
export class WizardComponent implements OnInit {

  currentQuestion: Question = { summary: "", question: CONSTANTS.REQUIREMENTS_INITIAL_PROMPT, suggestions: [] };
  answer: string = '';
  sessionId: string = '';
  isLoading = signal(false);

  wizardService = inject(WizardService);
  specService = inject(SpecService);
  loaderService = inject(LoaderService);
  router = inject(Router);

  ngOnInit() {
    if (!this.wizardService.project?.id) {
      this.router.navigate(['/dashboard']);
      return;
    }
    this.wizardService.startSession();
    this.wizardService.session$.subscribe((session) => {
      this.sessionId = session?.id || "";
    });
  }

  private getErrorMessage(err: any): string {
    const detail = err?.error?.detail;

    if (detail && typeof detail === "object" && detail.message) {
      return detail.message;
    }

    return FRIENDLY_WIZARD_ERROR;
  }

  private getReplyQuestion(reply: any): Question {
    if (!reply) {
      return {
        summary: CONSTANTS.ERROR_TEXT,
        question: "",
        suggestions: []
      };
    }

    if (typeof reply === "string") {
      try {
        const parsed = JSON.parse(reply);
        return {
          summary: parsed.summary || parsed.message || reply,
          question: parsed.question || "",
          suggestions: parsed.suggestions || []
        };
      } catch {
        return {
          summary: reply,
          question: "",
          suggestions: []
        };
      }
    }

    if (reply.message && !reply.summary) {
      return {
        summary: reply.message,
        question: "",
        suggestions: []
      };
    }

    return {
      summary: reply.summary || CONSTANTS.ERROR_TEXT,
      question: reply.question || "",
      suggestions: reply.suggestions || []
    };
  }

  private storeProjectData(data: any): void {
    if (data?.spec) {
      this.specService.setSpec(data.spec);
    }

    if (data?.nontech_artifacts_md) {
      this.specService.setNontechArtifacts(data.nontech_artifacts_md);
    }

    if (data?.technical_artifacts_md) {
      this.specService.setTechnicalArtifacts(data.technical_artifacts_md);
    }
  }

  private recordActivity(message: string, status: 'info' | 'running' | 'success' | 'error' = 'info'): void {
    const projectId = this.wizardService.project?.id;
    if (!projectId) return;

    this.wizardService.logProjectActivity(projectId, message, status).subscribe({
      error: err => console.warn('Activity message could not be saved:', err)
    });
  }

  private prepareDesignDocuments(): void {
    this.recordActivity('Preparing your design documents...', 'running');

    this.loaderService.startWithMessages([
      'Preparing your design documents...',
      'Organizing the screens and user flows...',
      'Writing the review checklist...',
      'Almost there...'
    ]);

    this.wizardService.sendMessage('prepare design documents', false).pipe(catchError(err => {
      console.error('Design document preparation failed:', err);
      this.recordActivity('I could not prepare the design documents just now.', 'error');
      this.loaderService.stop();
      this.currentQuestion.summary = 'Sorry, I could not prepare the design documents just now. Please try again in a moment.';
      this.currentQuestion.question = '';
      this.currentQuestion.suggestions = [];
      this.isLoading.set(false);
      return EMPTY;
    })).subscribe((res: Response | null) => {
      this.loaderService.stop();
      this.isLoading.set(false);

      if (res?.nontech_artifacts_md) {
        this.recordActivity('The design documents are ready for your review.', 'success');
        this.storeProjectData(res);
        this.router.navigate(['/spec-review']);
        return;
      }

      console.warn('Design document response did not include review documents:', res);
      this.recordActivity('The design documents need a little more time.', 'error');
      this.currentQuestion.summary = 'The design documents need a little more time. Please try again in a moment.';
      this.currentQuestion.question = '';
      this.currentQuestion.suggestions = [];
    });
  }

  handleSendMessage() {
    if (!this.answer) return;

    this.isLoading.set(true);
    this.currentQuestion.summary = "";
    this.currentQuestion.suggestions = [];
    this.currentQuestion.question = "";

    let tempAnswer = this.answer;
    this.answer = "";

    this.wizardService.sendMessage(tempAnswer).pipe(catchError(err => {
      console.error('Requirements request failed:', err);

      this.currentQuestion.summary = this.getErrorMessage(err);
      this.currentQuestion.question = "";
      this.currentQuestion.suggestions = [];
      this.isLoading.set(false);

      return EMPTY;
    }), map((res: Response | null) => {
      if (res?.stage === 'ARTIFACTS_NON_TECH' && res?.spec?.project_name && !res?.nontech_artifacts_md) {
        return {
          transitionToArtifacts: true,
          message: (res.reply as any)?.message || 'Great, I have enough to prepare the first set of design documents for your review.',
          spec: res.spec
        };
      }

      if (res?.spec?.project_name) {
        return {
          spec: res.spec,
          nontech_artifacts_md: res.nontech_artifacts_md,
          technical_artifacts_md: res.technical_artifacts_md
        };
      }

      if (res?.reply) {
        const replyQuestion = this.getReplyQuestion(res.reply);

        replyQuestion.suggestions = replyQuestion.suggestions?.map((suggestion: any) => {
          if (typeof suggestion === "string") {
            return { label: suggestion, selected: false };
          }

          return {
            label: suggestion.label || suggestion,
            selected: suggestion.selected || false
          };
        }) || [];

        return { reply: replyQuestion };
      }

      if (res?.raw_reply) {
        console.warn('Unexpected raw requirements reply:', res);
        return {
          reply: {
            summary: FRIENDLY_WIZARD_ERROR,
            question: "",
            suggestions: []
          }
        };
      }

      return null;
    })).subscribe((data: any) => {
      if (data?.transitionToArtifacts) {
        this.storeProjectData(data);
        this.currentQuestion.summary = data.message;
        this.currentQuestion.question = '';
        this.currentQuestion.suggestions = [];
        this.prepareDesignDocuments();
        return;
      }

      if (data?.spec?.project_name) {
        this.storeProjectData(data);

        this.router.navigate(['/spec-review']);
      } else {
        const reply = data?.reply;
        this.currentQuestion.summary = (reply as Question)?.summary || CONSTANTS.ERROR_TEXT;
        this.currentQuestion.question = (reply as Question)?.question || "";
        this.currentQuestion.suggestions = (reply as Question)?.suggestions || [];
        this.answer = "";
      }

      this.isLoading.set(false);
    });
  }

  selectSuggestion(suggestion: { label: string, selected: boolean }) {
    this.answer = '';
    suggestion.selected = !suggestion.selected;
    this.currentQuestion?.suggestions?.map(suggestion => {
      if (suggestion.selected) {
        this.answer += suggestion.label + ", ";
      }
    });
    this.answer = this.answer.substring(0, this.answer.length - 2);
  }

  back() {
    this.router.navigate(['/dashboard']);
  }

}