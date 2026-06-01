import { Component, inject, Input, OnInit, signal, ChangeDetectionStrategy, ElementRef, ViewChild, AfterViewInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MarkdownModule } from 'ngx-markdown';
import { WizardService } from '../requirements/services/wizard-service';
import { SpecService } from './services/spec.service';
import { catchError, of } from 'rxjs';
import { LoaderService } from '../../shared/services/loader.service';

const FRIENDLY_CHAT_ERROR = 'Sorry, something went wrong while working on your request. Please try again in a moment.';
const FRIENDLY_EMPTY_REPLY = 'Thanks, I am still working on that. Please try again in a moment.';

type ChatMessage = {
  id: number;
  text: string;
  type: string;
  status?: 'info' | 'running' | 'success' | 'error';
};

@Component({
  selector: 'app-chatbox',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownModule],
  templateUrl: './chatbox.html',
  styleUrl: './chatbox.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class ChatboxComponent implements OnInit, AfterViewInit, OnDestroy {

  wizardService = inject(WizardService);
  specService = inject(SpecService);
  loaderService = inject(LoaderService);
  chatHistory = signal<ChatMessage[]>([]);
  chatMessage: string = '';
  sendBtnDisabled = signal<boolean>(false);
  sendBtnText = signal<string>("Send");
  isThinking = signal<boolean>(false);
  @Input() isPreviewMode: boolean = false;
  @Input() isStackblitzActive: boolean = false;
  @ViewChild('chatHistoryElement') chatHistoryElement!: ElementRef;
  private observer?: MutationObserver;

  constructor() { }

  ngOnInit() {
    const projectId = this.wizardService.project?.id;

    if (!projectId) {
      return;
    }

    this.wizardService.getProjectMessages(projectId).subscribe({
      next: (res) => {
        const history = (res.messages || []).map((msg: any, index: number) => {
          return {
            id: msg.id || index + 1,
            text: msg.metadata?.error ? FRIENDLY_CHAT_ERROR : msg.content,
            type: msg.metadata?.kind === "activity" ? "activity" : msg.role === "user" ? "user" : "system",
            status: msg.metadata?.status || "info",
          };
        });

        this.chatHistory.set(history);
      },
      error: (err) => {
        console.error("Failed to load chat history:", err);
      }
    });
  }

  ngAfterViewInit() {
    // Only initialize MutationObserver on client-side (browser environment)
    if (typeof window !== 'undefined' && MutationObserver) {
      this.observer = new MutationObserver(() => this.scrollToBottom());
      this.observer.observe(this.chatHistoryElement.nativeElement, {
        childList: true, // Watch for new messages
        subtree: true,   // Watch for changes inside messages (like markdown updates)
        characterData: true // Watch for streaming text changes
      });
    }
  }

  ngOnDestroy() {
    // Clean up observer when component is destroyed
    if (this.observer) {
      this.observer.disconnect();
    }
  }

  private resetSendState(): void {
    this.sendBtnDisabled.set(false);
    this.isThinking.set(false);
    this.sendBtnText.set("Send");
  }

  private addSystemMessage(text: string): void {
    this.chatHistory.update((prev) => [
      ...prev,
      {
        type: "system",
        text,
        id: prev.length + 1
      }
    ]);
  }

  addActivityMessage(text: string, status: 'info' | 'running' | 'success' | 'error' = 'info'): void {
    this.chatHistory.update((prev) => [
      ...prev,
      {
        type: "activity",
        status,
        text,
        id: prev.length + 1
      }
    ]);
  }

  private getErrorMessage(err: any): string {
    const detail = err?.error?.detail;

    if (detail && typeof detail === "object" && detail.message) {
      return detail.message;
    }

    return FRIENDLY_CHAT_ERROR;
  }

  private applyProjectResponse(response: any, options: { updateNontechArtifacts?: boolean } = {}): void {
    if (response?.spec) {
      this.specService.setSpec(response.spec);
    }
    if (options.updateNontechArtifacts !== false && response?.nontech_artifacts_md) {
      this.specService.setNontechArtifacts(response.nontech_artifacts_md);
    }
    if (response?.technical_artifacts_md) {
      this.specService.setTechnicalArtifacts(response.technical_artifacts_md);
    }
    if (response?.angular_code_files) {
      this.specService.setAngularCode(response.angular_code_files);
    }
    if (response?.needs_redeploy !== undefined) {
      this.specService.needsRedeploy.set(!!response.needs_redeploy);
    }
  }

  private needsDesignDocumentRefresh(response: any): boolean {
    return response?.stage === 'ARTIFACTS_NON_TECH';
  }

  private refreshDesignDocuments(): void {
    this.addActivityMessage('Updating your design documents...', 'running');
    this.loaderService.startWithMessages([
      'Updating your design documents...',
      'Applying your latest changes...',
      'Refreshing the review materials...',
      'Almost there...'
    ]);

    this.wizardService.sendMessage('prepare updated design documents', false).pipe(catchError(err => {
      console.error('Design document refresh failed:', err);
      this.loaderService.stop();
      this.addActivityMessage('I could not update the design documents just now.', 'error');
      this.addSystemMessage(this.getErrorMessage(err));
      this.resetSendState();
      return of(null);
    })).subscribe(response => {
      this.loaderService.stop();

      if (response) {
        this.applyProjectResponse(response);
        this.addActivityMessage('The design documents are updated and ready for review.', 'success');
        this.addSystemMessage(this.getReplyText(response));
      }

      this.resetSendState();
      console.log('Design documents refreshed: ', response);
    });
  }

  private getReplyText(response: any): string {
    const reply = response?.reply;

    if (!reply) {
      console.warn('Empty chat reply received:', response);
      return FRIENDLY_EMPTY_REPLY;
    }

    if (typeof reply === "string") {
      try {
        const parsed = JSON.parse(reply);
        return Object.values(parsed).join(" ");
      } catch {
        return reply;
      }
    }

    if (reply.message) {
      return reply.message;
    }

    if (reply.summary) {
      let text = reply.summary;

      if (reply.question) {
        text += " " + reply.question;
      }

      if (reply.suggestions) {
        text += " " + reply.suggestions;
      }

      return text;
    }

    console.warn('Unexpected chat reply shape:', response);
    return FRIENDLY_EMPTY_REPLY;
  }

  sendChatMessage() {
    if (this.chatMessage) {
      this.sendBtnDisabled.set(true);
      this.isThinking.set(true);
      this.sendBtnText.set("Thinking...");
      this.chatHistory.update((prev) => [...prev, { type: "user", text: this.chatMessage, id: prev.length + 1 }]);
      let tempMessage = this.chatMessage;
      this.chatMessage = '';

      //code refinement flow when isStackblitzActive is true
      if (this.isStackblitzActive) {
        this.wizardService.sendMessage(tempMessage).pipe(catchError(err => {
          console.error('Chat request failed:', err);
          this.addSystemMessage(this.getErrorMessage(err));
          this.resetSendState();
          return of(null); // fallback value
        })).subscribe(response => {
          if (response) {
            this.applyProjectResponse(response);

            const systemResponse = this.getReplyText(response);
            this.addSystemMessage(systemResponse);
          }
          this.resetSendState();
          console.log('Response received: ', response);
        });
      } else {
        //spec review flow
        this.wizardService.sendMessage("change", false).pipe(catchError(err => {
          console.error('Chat revision request failed:', err);
          this.addSystemMessage(this.getErrorMessage(err));
          this.resetSendState();
          return of(null);
        })).subscribe(response => {
          if (response) {
            this.wizardService.sendMessage(tempMessage).pipe(catchError(err => {
              console.error('Chat follow-up request failed:', err);
              this.addSystemMessage(this.getErrorMessage(err));
              this.resetSendState();
              return of(null);
            })).subscribe(response => {
              if (response) {
                this.applyProjectResponse(response, {
                  updateNontechArtifacts: !this.needsDesignDocumentRefresh(response)
                });

                if (this.needsDesignDocumentRefresh(response)) {
                  this.refreshDesignDocuments();
                  return;
                }

                const systemResponse = this.getReplyText(response);
                this.resetSendState();
                console.log('Response received: ', response);
                this.addSystemMessage(systemResponse);
              }
              // loading cleanup only after inner request completes
              this.resetSendState();
            });
          } else {
            this.resetSendState();
          }
        });
      }

    }
  }

  private scrollToBottom(): void {
    const el = this.chatHistoryElement.nativeElement;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }

}
