import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { WizardService } from '../../services/wizard-service';
import { SpecService } from '../../../spec-review/services/spec.service';
import { Question, Response, Spec } from '../../models/response.model';
import { CONSTANTS } from '../../config/sample-questions';
import { catchError, map, of } from 'rxjs';
import { HeaderComponent } from '../../../../shared/components/header/header.component';

@Component({
  selector: 'app-wizard',
  templateUrl: './wizard.html',
  styleUrls: ['./wizard.scss'],
  standalone: true,
  imports: [FormsModule, HeaderComponent]
})
export class WizardComponent implements OnInit {

  currentQuestion: Question = { summary: CONSTANTS.REQUIREMENTS_INITIAL_PROMPT, question: "", suggestions: [] };
  answer: string = '';
  sessionId: string = '';
  isLoading = signal(false);
  userId = '';
  projectTitle = '';
  projectDescription = '';
  projectCreated = false;

  wizardService = inject(WizardService);
  specService = inject(SpecService);
  router = inject(Router);

  ngOnInit() {
    this.wizardService.startSession();
    this.wizardService.session$.subscribe((session) => {
      this.sessionId = session?.id || "";
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
      console.log('Error caught:', err);
      return of(null);
    }), map((res: Response | null) => {
      if (res?.spec?.project_name) {
        return {
          reply: res.spec,
          nontech_artifacts_md: res.nontech_artifacts_md,
          technical_artifacts_md: res.technical_artifacts_md
        };
      } else if (res?.reply?.suggestions) {
        res.reply.suggestions = res?.reply.suggestions?.map((suggestion) => {
          return { label: suggestion, selected: false };
        }) || [];
        return { reply: res.reply };
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

  createProject(): void {
    if (!this.userId || !this.projectTitle) {
      alert('Please enter user ID and project title.');
      return;
    }

    this.wizardService.createProject(
      this.userId,
      this.projectTitle,
      this.projectDescription
    );

    this.projectCreated = true;
}

}
