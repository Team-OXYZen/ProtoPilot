import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { WizardService } from '../../services/wizard-service';
import { SpecService } from '../../../spec-review/services/spec.service';
import { Question, Response, Spec } from '../../models/response.model';
import { CONSTANTS } from '../../config/sample-questions';
import { catchError, EMPTY, map } from 'rxjs';
import { HeaderComponent } from '../../../../shared/components/header/header.component';

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

    if (typeof detail === "string") {
      return detail;
    }

    if (detail?.message) {
      return detail.message;
    }

    return err?.message || CONSTANTS.ERROR_TEXT;
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

  handleSendMessage() {
    if (!this.answer) return;

    this.isLoading.set(true);
    this.currentQuestion.summary = "";
    this.currentQuestion.suggestions = [];
    this.currentQuestion.question = "";

    let tempAnswer = this.answer;
    this.answer = "";

    this.wizardService.sendMessage(tempAnswer).pipe(catchError(err => {
      console.log('Error caught:', err);

      this.currentQuestion.summary = `Error: ${this.getErrorMessage(err)}`;
      this.currentQuestion.question = "";
      this.currentQuestion.suggestions = [];
      this.isLoading.set(false);

      return EMPTY;
    }), map((res: Response | null) => {
      if (res?.spec?.project_name) {
        return {
          reply: res.spec,
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
        return {
          reply: {
            summary: res.raw_reply,
            question: "",
            suggestions: []
          }
        };
      }

      return null;
    })).subscribe((data: any) => {
      const reply = data?.reply;

      if ((reply as Spec)?.project_name) {
        // Store results in services and navigate to spec-review
        this.specService.setSpec(reply);

        if (data?.nontech_artifacts_md) {
          this.specService.setNontechArtifacts(data.nontech_artifacts_md);
        }

        if (data?.technical_artifacts_md) {
          this.specService.setTechnicalArtifacts(data.technical_artifacts_md);
        }

        this.router.navigate(['/spec-review']);
      } else {
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