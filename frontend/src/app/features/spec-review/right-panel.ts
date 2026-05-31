import { JsonPipe, CommonModule } from '@angular/common';
import { Component, inject, Input, OnChanges, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MarkdownModule } from 'ngx-markdown';
import { SpecService } from './services/spec.service';
import mermaid from 'mermaid';
import { LivePreviewComponent } from './components/live-preview/live-preview.component';
import { WizardService } from '../requirements/services/wizard-service';
import { finalize } from 'rxjs';

@Component({
  selector: 'app-right-panel',
  standalone: true,
  imports: [JsonPipe, MarkdownModule, CommonModule, FormsModule, LivePreviewComponent],
  templateUrl: './right-panel.html',
  styleUrl: './right-panel.scss'
})
export class RightPanelComponent implements OnChanges, AfterViewInit {

  @Input() selectedSection: string = '';
  @Input() mdText: string = '';
  @Input() isPreviewMode: boolean = false;
  @Input() selectedFile: string = '';
  @ViewChild('mermaidContainer', { static: false }) mermaidContainer?: ElementRef;

  specService = inject(SpecService);
  wizardService = inject(WizardService);
  githubExportLoading = false;
  githubConnectLoading = false;
  githubConnected = false;
  githubUsername = '';
  githubOwner = '';
  githubRepo = '';
  confluenceSpaceKey = '';
  jiraTasksLoading = false;
  confluenceExportLoading = false;
  integrationError = '';
  integrationMessage = '';

  constructor() {
    mermaid.initialize({ startOnLoad: false });
  }

  ngAfterViewInit() {
    if (this.isMermaidDiagram(this.mdText)) {
      this.renderMermaid();
    }
    this.loadGitHubConnectionStatus();
  }

  ngOnChanges() {
    if (this.isPreviewMode && this.isMermaidDiagram(this.mdText)) {
      setTimeout(() => {
        this.renderMermaid();
      }, 0);
    }
  }

  isMermaidDiagram(content: string): boolean {
    if (!content) return false;
    const mermaidPatterns = [
      /^```mermaid/m,
      /^graph\s+(TD|LR|RL|BT|TB)/m,
      /^flowchart\s+(TD|LR|RL|BT|TB)/m,
      /^sequenceDiagram/m,
      /^classDiagram/m,
      /^stateDiagram/m,
      /^erDiagram/m,
      /^pie\s+title/m,
      /^gantt/m,
      /^journey/m
    ];
    return mermaidPatterns.some(pattern => pattern.test(content));
  }

  async renderMermaid() {
    try {
      if (this.mermaidContainer) {
        // Extract mermaid code from markdown code block
        let mermaidCode = this.extractMermaidCode(this.mdText);
        mermaidCode = mermaidCode.replace(/ \(/g, ' &lpar;').replace(/\)\)/g, '&rpar;)').replace(/\) /g, '&rpar; ');        
        console.log('Extracted Mermaid Code:', mermaidCode);

        const { svg } = await mermaid.render('graphDiv', mermaidCode);

        const container = this.mermaidContainer.nativeElement;
        container.innerHTML = svg;
      }
    } catch (error) {
      console.error('Error rendering mermaid diagram:', error);
    }
  }

  extractMermaidCode(content: string): string {
    // Try to extract from markdown code block first
    const codeBlockMatch = content.match(/```mermaid\n([\s\S]*?)\n```/);
    if (codeBlockMatch && codeBlockMatch[1]) {
      return codeBlockMatch[1].trim();
    }
    // If no code block, return the content as is
    return content.trim();
  }

  isCodePreview(): boolean {
    return this.selectedFile === 'code-preview';
  }

  getGeneratedFiles(): Record<string, string> | null {
    return this.specService.angular_code_files();
  }

  hasGeneratedCode(): boolean {
    const generatedCode = this.specService.angular_code_files();
    return !!generatedCode && Object.keys(generatedCode).length > 0;
  }

  exportToGitHub(): void {
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      this.integrationError = 'Missing project or session id.';
      return;
    }

    if (!this.githubOwner.trim() || !this.githubRepo.trim()) {
      this.integrationError = 'Enter a GitHub owner and repository.';
      return;
    }

    if (!this.githubConnected) {
      this.integrationError = 'Connect your GitHub account before exporting.';
      return;
    }

    this.githubExportLoading = true;
    this.integrationError = '';
    this.integrationMessage = '';

    this.wizardService.exportGeneratedCodeToGithub(
      projectId,
      sessionId,
      this.githubOwner.trim(),
      this.githubRepo.trim()
    ).pipe(
      finalize(() => {
        this.githubExportLoading = false;
      })
    ).subscribe({
      next: (result) => {
        this.integrationMessage = result?.pull_request_url
          ? `GitHub export complete: ${result.pull_request_url}`
          : 'GitHub export complete.';
      },
      error: (error) => {
        this.integrationError = this.formatIntegrationError(error, 'GitHub export failed.');
      },
    });
  }

  connectGitHub(): void {
    this.githubConnectLoading = true;
    this.integrationError = '';
    this.integrationMessage = '';

    this.wizardService.startGitHubOAuth().pipe(
      finalize(() => {
        this.githubConnectLoading = false;
      })
    ).subscribe({
      next: (result) => {
        if (result?.authorization_url) {
          window.location.href = result.authorization_url;
          return;
        }
        this.integrationError = 'GitHub authorization URL was not returned.';
      },
      error: (error) => {
        this.integrationError = this.formatIntegrationError(error, 'GitHub connection failed.');
      },
    });
  }

  private loadGitHubConnectionStatus(): void {
    this.wizardService.getGitHubConnectionStatus().subscribe({
      next: (result) => {
        this.githubConnected = !!result?.connected;
        this.githubUsername = result?.github_username || '';
      },
      error: () => {
        this.githubConnected = false;
        this.githubUsername = '';
      },
    });
  }

  createJiraTasks(): void {
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      this.integrationError = 'Missing project or session id.';
      return;
    }

    this.jiraTasksLoading = true;
    this.integrationError = '';
    this.integrationMessage = '';

    this.wizardService.createJiraTasks(projectId, sessionId).pipe(
      finalize(() => {
        this.jiraTasksLoading = false;
      })
    ).subscribe({
      next: () => {
        this.integrationMessage = 'Jira product plan creation requested.';
      },
      error: (error) => {
        this.integrationError = this.formatIntegrationError(error, 'Jira product plan creation failed.');
      },
    });
  }

  exportArtifactsToConfluence(): void {
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      this.integrationError = 'Missing project or session id.';
      return;
    }

    this.confluenceExportLoading = true;
    this.integrationError = '';
    this.integrationMessage = '';

    this.wizardService.exportArtifactsToConfluence(projectId, sessionId, this.confluenceSpaceKey.trim()).pipe(
      finalize(() => {
        this.confluenceExportLoading = false;
      })
    ).subscribe({
      next: () => {
        this.integrationMessage = 'Confluence artifact export requested.';
      },
      error: (error) => {
        this.integrationError = this.formatIntegrationError(error, 'Confluence artifact export failed.');
      },
    });
  }

  private formatIntegrationError(error: any, fallback: string): string {
    return error?.error?.detail || error?.message || fallback;
  }

  createStackBlitzProject(): any {
    const generatedCode = this.specService.angular_code_files();
    if (!generatedCode) return null;

    return {
      files: generatedCode,
      title: 'Generated Angular Project',
      description: 'Auto-generated Angular project from ProtoPilot',
    };
  }

  openStackBlitz(): void {
    const generatedCode = this.specService.angular_code_files();
    if (!generatedCode) {
      console.error('No generated code found');
      return;
    }

    // StackBlitz API endpoint
    const url = 'https://stackblitz.com/api/v1/angular';
    
    // Create form data
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = url;
    form.target = '_blank';

    // Add files to form
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'project[files]';
    input.value = JSON.stringify(generatedCode);
    form.appendChild(input);

    // Add title
    const titleInput = document.createElement('input');
    titleInput.type = 'hidden';
    titleInput.name = 'project[title]';
    titleInput.value = 'ProtoPilot Generated App';
    form.appendChild(titleInput);

    // Add description
    const descInput = document.createElement('input');
    descInput.type = 'hidden';
    descInput.name = 'project[description]';
    descInput.value = 'Auto-generated Angular application from ProtoPilot';
    form.appendChild(descInput);

    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  }

  get selectedData() {
    return this.specService.spec()[this.selectedSection];
  }

  get isStringArray(): boolean {
    return Array.isArray(this.selectedData) && this.selectedData.every(item => typeof item === 'string');
  }

  get isObjectArray(): boolean {
    return Array.isArray(this.selectedData) && this.selectedData.length > 0 && typeof this.selectedData[0] === 'object' && !Array.isArray(this.selectedData[0]);
  }

  get isObject(): boolean {
    return typeof this.selectedData === 'object' && !Array.isArray(this.selectedData) && this.selectedData !== null;
  }

  getObjectKeys(obj: any): string[] {
    return Object.keys(obj);
  }

  toTitleCase(str: string): string {
    return str?.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  }

}
