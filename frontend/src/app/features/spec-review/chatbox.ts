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
          return of(null); // fallback value
        })).subscribe(response => {
          if (response) {
            if((response as any).angular_code_files){
              this.specService.setAngularCode((response as any).angular_code_files);
            }
            if ((response as any).nontech_artifacts_md) {
              this.specService.setNontechArtifacts((response as any).nontech_artifacts_md);
            }
            if ((response as any).technical_artifacts_md) {
              this.specService.setTechnicalArtifacts((response as any).technical_artifacts_md);
            }

            let systemResponse = "";

            if (typeof response.reply == "string") {
              systemResponse = Object.values(JSON.parse((response.reply) as any)).join(" ");
            } else if (response.reply.message) {
              systemResponse = response.reply.message;
            } else if (response.reply && response.reply.summary) {
              systemResponse = response.reply.summary;
              if (response.reply.question) {
                systemResponse += " " + response.reply.question;
              }
              if (response.reply.suggestions) {
                systemResponse += " " + response.reply.suggestions;
              }
            }
            this.chatHistory.update((prev) => [...prev, { type: "system", text: systemResponse, id: prev.length + 1 }]);
          }
          this.sendBtnDisabled.set(false);
          this.isThinking.set(false);
          this.sendBtnText.set("Send");
          console.log('Response received: ', response);
        });
      } else {
        //spec review flow
        this.wizardService.sendMessage("change", false).pipe(catchError(err => {
          console.log('Error caught:', err);
          this.isThinking.set(false);
          this.sendBtnDisabled.set(false);
          this.sendBtnText.set("Send");
          return of(null);
        })).subscribe(response => {
          if (response) {
            this.wizardService.sendMessage(tempMessage).pipe(catchError(err => {
              console.log('Error caught:', err);
              this.isThinking.set(false);
              this.sendBtnDisabled.set(false);
              this.sendBtnText.set("Send");
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

                let systemResponse = "";
                if (typeof response.reply == "string") {
                  systemResponse = Object.values(JSON.parse((response.reply) as any)).join(" ");
                } else if (response.reply?.message) {
                  systemResponse = response.reply.message;
                } else if (response.reply?.summary) {
                  systemResponse = response.reply.summary;
                  if (response.reply.question) systemResponse += " " + response.reply.question;
                  if (response.reply.suggestions) systemResponse += " " + response.reply.suggestions;
                }
                this.sendBtnDisabled.set(false);
                this.isThinking.set(false);
                this.sendBtnText.set("Send");
                console.log('Response received: ', response);
                this.chatHistory.update((prev) => [...prev, { type: "system", text: systemResponse, id: prev.length + 1 }]);
              }
              // loading cleanup only after inner request completes
              this.sendBtnDisabled.set(false);
              this.isThinking.set(false);
              this.sendBtnText.set("Send");
            });
          } else {
            this.sendBtnDisabled.set(false);
            this.isThinking.set(false);
            this.sendBtnText.set("Send");
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
