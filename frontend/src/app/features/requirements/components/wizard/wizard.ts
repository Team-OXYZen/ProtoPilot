import { ChangeDetectionStrategy, ChangeDetectorRef, Component, ElementRef, inject, OnInit, Output, EventEmitter, signal, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { WizardService } from '../../services/wizard-service';
import { Question, Response, Spec } from '../../models/response.model';
import { CONSTANTS } from '../../config/sample-questions';
import { catchError, map, of } from 'rxjs';

@Component({
  selector: 'app-wizard',
  templateUrl: './wizard.html',
  styleUrls: ['./wizard.scss'],
  standalone: true,
  imports: [FormsModule]
})
export class WizardComponent implements OnInit {

  @Output() onComplete = new EventEmitter<any>();

  currentQuestion: Question = { summary: CONSTANTS.REQUIREMENTS_INITIAL_PROMPT, question: "", suggestions: [] };
  answer: string = '';
  sessionId: string = '';
  isLoading = signal(false);
  @ViewChild('textAreaRef') textAreaRef!: ElementRef<HTMLTextAreaElement>;


  wizardService = inject(WizardService);

  constructor() { }

  ngOnInit() {
    this.wizardService.startSession();
    this.wizardService.session$.subscribe((session) => {
      this.sessionId = session?.id || "";
      console.log("Session set to", this.sessionId);
    })
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
      return of(null); // fallback value
    }), map((res: Response | null) => {
      console.log("Response received: ", res);
      if (res?.spec?.project_name) {
        return {
          reply: res.spec,
          nontech_artifacts_md: res.nontech_artifacts_md,
          technical_artifacts_md: res.technical_artifacts_md
        };
      } else if (res?.reply?.suggestions) {
        res.reply.suggestions = res?.reply.suggestions?.map((suggestion) => {
          return { label: suggestion, selected: false }
        }) || [];
        return { reply: res.reply };
      }
      return null;
    })).subscribe((data: any) => {
      const reply = data?.reply;
      console.log(reply)
      if((reply as Spec)?.project_name) {
        this.currentQuestion.summary = CONSTANTS.REQUIREMENTS_DONE_TEXT;
        this.currentQuestion.question = CONSTANTS.REQUIREMENTS_DONE_SUBTEXT;
        // Emit complete data with spec and artifacts
        const completeData = {
          spec: reply,
          nontech_artifacts_md: data?.nontech_artifacts_md || {},
          technical_artifacts_md: data?.technical_artifacts_md || {}
        };
        this.onComplete.emit(completeData);
      } else {
        this.currentQuestion.summary = (reply as Question)?.summary || CONSTANTS.ERROR_TEXT;
        this.currentQuestion.question = (reply as Question)?.question || "";
        this.currentQuestion.suggestions = (reply as Question)?.suggestions || [];
        this.answer = "";
      }
      this.isLoading.set(false);
    })
  }

  selectSuggestion(suggestion: { label: string, selected: boolean }) {
    this.answer = '';
    suggestion.selected = !suggestion.selected;
    this.currentQuestion?.suggestions?.map(suggestion => {
      if (suggestion.selected) {
        this.answer += suggestion.label + ", ";
      }
    });
    this.answer = this.answer.substring(0, this.answer.length - 2)
  }

  back() {
  }

}