import { Component, inject, Input, OnInit, signal, ChangeDetectionStrategy, ElementRef, ViewChild, AfterViewInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MarkdownModule } from 'ngx-markdown';
import { WizardService } from '../requirements/services/wizard-service';
import { SpecService } from './services/spec.service';
import { catchError, of } from 'rxjs';

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
  chatHistory = signal<[{ id: number, text: string, type: string }] | any>([]);
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
            text: msg.content,
            type: msg.role === "user" ? "user" : "system"
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

  private getErrorMessage(err: any): string {
    const detail = err?.error?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (detail?.message) {
      return detail.message;
    }

    return err?.message || "Unknown backend error";
  }

  private getReplyText(response: any): string {
    const reply = response?.reply;

    if (!reply) {
      return response?.raw_reply || "";
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

    return response?.raw_reply || JSON.stringify(reply);
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
          console.log('Error caught:', err);
          this.addSystemMessage(`Error: ${this.getErrorMessage(err)}`);
          this.resetSendState();
          return of(null); // fallback value
        })).subscribe(response => {
          if (response) {
            if((response as any).angular_code_files){
              this.specService.setAngularCode((response as any).angular_code_files);
            }
            if ((response as any).needs_redeploy !== undefined) {
              this.specService.needsRedeploy.set(!!(response as any).needs_redeploy);
            }
            if ((response as any).nontech_artifacts_md) {
              this.specService.setNontechArtifacts((response as any).nontech_artifacts_md);
            }
            if ((response as any).technical_artifacts_md) {
              this.specService.setTechnicalArtifacts((response as any).technical_artifacts_md);
            }

            const systemResponse = this.getReplyText(response);
            this.addSystemMessage(systemResponse);
          }
          this.resetSendState();
          console.log('Response received: ', response);
        });
      } else {
        //spec review flow
        this.wizardService.sendMessage("change", false).pipe(catchError(err => {
          console.log('Error caught:', err);
          this.addSystemMessage(`Error: ${this.getErrorMessage(err)}`);
          this.resetSendState();
          return of(null);
        })).subscribe(response => {
          if (response) {
            this.wizardService.sendMessage(tempMessage).pipe(catchError(err => {
              console.log('Error caught:', err);
              this.addSystemMessage(`Error: ${this.getErrorMessage(err)}`);
              this.resetSendState();
              return of(null);
            })).subscribe(response => {
              if (response) {
                if ((response as any).spec) {
                  this.specService.setSpec((response as any).spec);
                }
                if ((response as any).nontech_artifacts_md) {
                  this.specService.setNontechArtifacts((response as any).nontech_artifacts_md);
                }
                if ((response as any).technical_artifacts_md) {
                  this.specService.setTechnicalArtifacts((response as any).technical_artifacts_md);
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
