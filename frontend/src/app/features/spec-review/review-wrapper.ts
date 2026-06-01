import { Component, effect, HostListener, inject, OnDestroy, OnInit, signal, ViewChild } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { IconDefinition } from '@fortawesome/fontawesome-common-types';
import { faAtlassian, faConfluence, faGithub, faJira } from '@fortawesome/free-brands-svg-icons';
import JSZip from 'jszip';
import mermaid from 'mermaid';
import { LeftPanelComponent } from './left-panel';
import { RightPanelComponent } from './right-panel';
import { WizardService } from '../requirements/services/wizard-service';
import { SpecService } from './services/spec.service';
import { catchError, finalize, interval, of, Subscription, switchMap, takeWhile } from 'rxjs';
import { ChatboxComponent } from './chatbox';
import { LoaderService } from '../../shared/services/loader.service';
import { HeaderComponent } from '../../shared/components/header/header.component';

@Component({
  selector: 'app-review-wrapper',
  standalone: true,
  imports: [LeftPanelComponent, RightPanelComponent, ChatboxComponent, HeaderComponent],
  templateUrl: './review-wrapper.html',
  styleUrl: './review-wrapper.scss'
})
export class ReviewWrapperComponent implements OnInit, OnDestroy {

  @ViewChild(ChatboxComponent) chatbox!: ChatboxComponent;

  selectedFile: string = '';
  selectedSection: string = '';
  showSpecView = signal(false);
  files = signal<string[]>([]);
  showExportMenu = signal(false);
  githubExportLoading = signal(false);
  githubConnectLoading = signal(false);
  githubDisconnectLoading = signal(false);
  githubConnected = signal(false);
  githubUsername = signal('');
  atlassianConnectLoading = signal(false);
  atlassianDisconnectLoading = signal(false);
  atlassianConnected = signal(false);
  atlassianUsername = signal('');
  jiraTasksLoading = signal(false);
  confluenceExportLoading = signal(false);
  integrationError = signal('');
  integrationMessage = signal('');
  exportIcons = {
    github: this.toSvgIcon(faGithub),
    atlassian: this.toSvgIcon(faAtlassian),
    jira: this.toSvgIcon(faJira),
    confluence: this.toSvgIcon(faConfluence),
  };

  private pollSub?: Subscription;
  private oauthPoll?: ReturnType<typeof setInterval>;
  private oauthMessageHandler?: (e: MessageEvent) => void;
  private atlassianOauthPoll?: ReturnType<typeof setInterval>;
  private atlassianOauthMessageHandler?: (e: MessageEvent) => void;
  private readonly artifactOrder = [
    'Product_Brief.md',
    'User_Needs_and_Actions.md',
    'User_Stories_for_Jira.md',
    'User_Journey_and_Screens.md',
    'Screen_and_Interaction_Plan.md',
    'Prototype_Acceptance_Checklist.md',
    'Technical_Architecture_Diagram.mmd',
    'Technical_Architecture_Notes.md',
    'Data_Model_Diagram.mmd',
    'Data_Dictionary.md',
    'Backend_API_Reference.md',
    'Codebase_Organization.md',
  ];

  wizardService = inject(WizardService);
  specService = inject(SpecService);
  loaderService = inject(LoaderService);
  router = inject(Router);
  private route = inject(ActivatedRoute);

  private toSvgIcon(icon: IconDefinition): { viewBox: string; paths: string[] } {
    const [width, height, , , svgPathData] = icon.icon;
    return {
      viewBox: `0 0 ${width} ${height}`,
      paths: Array.isArray(svgPathData) ? svgPathData : [svgPathData],
    };
  }

  constructor() {
    // Auto-refresh file list when non-tech artifacts change (e.g. after chatbox modification)
    effect(() => {
      const nontechArtifacts = this.specService.nontech_artifacts_md();
      const technicalArtifacts = this.specService.technical_artifacts_md();

      if (nontechArtifacts && this.selectedFile !== 'code-preview') {
        const allFiles = this.sortArtifactFiles(Object.keys(nontechArtifacts));

        if (technicalArtifacts) {
          allFiles.push(...this.sortArtifactFiles(Object.keys(technicalArtifacts)));
        }
        this.files.set(allFiles);
        if (allFiles.length > 0 && !allFiles.includes(this.selectedFile)) {
          this.selectedFile = allFiles[0];
        }
      }
    });
  }

  hasNonTechArtifacts() {
    return this.specService.nontech_artifacts_md() && Object.keys(this.specService.nontech_artifacts_md() as any).length > 0;
  }

  hasTechnicalArtifacts() {
    return this.specService.technical_artifacts_md() && Object.keys(this.specService.technical_artifacts_md() as any).length > 0;
  }

  hasGeneratedCode() {
    return this.specService.angular_code_files() && Object.keys(this.specService.angular_code_files() as any).length > 0;
  }

  hasJavaCode() {
    return this.specService.java_code_files() && Object.keys(this.specService.java_code_files() as any).length > 0;
  }

  ngOnInit() {
    if (!this.hasReviewContext()) {
      this.router.navigate(['/dashboard']);
      return;
    }

    const spec = this.specService.spec();
    if (spec && Object.keys(spec).length > 0) {
      this.selectedSection = Object.keys(spec).sort()[0];
    }
    if (this.hasNonTechArtifacts()) {
      const allFiles = this.sortArtifactFiles(Object.keys(this.specService.nontech_artifacts_md() as any));
      this.files.set(allFiles);
      this.selectedFile = allFiles[0] || '';
    }
    if (this.hasGeneratedCode()) {
      this.selectedFile = 'code-preview';
    }
    const projectId = this.wizardService.project?.id;
    if (projectId && this.hasJavaCode()) {
      this.wizardService.getDeployStatus(projectId).subscribe({
        next: (s) => {
          if (s.status === 'running') this.specService.setDeployStatus('running', s.url);
        },
        error: () => {}
      });
    }
    this.loadGitHubConnectionStatus();
    this.loadAtlassianConnectionStatus();

    this.route.queryParams.subscribe(params => {
      if (params['github_connected'] === '1') {
        this.loadGitHubConnectionStatus();
        this.recordActivity('GitHub account connected successfully.', 'success');
        this.router.navigate([], { replaceUrl: true, queryParams: {} });
      }
      if (params['atlassian_connected'] === '1') {
        this.loadAtlassianConnectionStatus();
        this.recordActivity('Atlassian account connected successfully.', 'success');
        this.router.navigate([], { replaceUrl: true, queryParams: {} });
      }
    });
  }

  @HostListener('document:click')
  closeExportMenu(): void {
    this.showExportMenu.set(false);
  }

  private hasReviewContext(): boolean {
    const spec = this.specService.spec();
    return Boolean(
      this.wizardService.project?.id ||
      (spec && Object.keys(spec).length > 0) ||
      this.hasNonTechArtifacts() ||
      this.hasTechnicalArtifacts() ||
      this.hasGeneratedCode() ||
      this.hasJavaCode()
    );
  }

  onSectionSelect(section: string) {
    this.selectedSection = section;
  }

  toggleSpecView() {
    this.showSpecView.update(v => !v);
  }

  isStackblitzActive() {
    return this.selectedFile === 'code-preview';
  }

  toggleExportMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.showExportMenu.update((value) => !value);
  }

  private recordActivity(message: string, status: 'info' | 'running' | 'success' | 'error' = 'info'): void {
    this.chatbox?.addActivityMessage(message, status);

    const projectId = this.wizardService.project?.id;
    if (!projectId) {
      console.warn('Could not save activity because project context is missing:', { message, status });
      return;
    }

    this.wizardService.logProjectActivity(projectId, message, status).subscribe({
      error: (error) => console.error('Failed to save project activity:', error),
    });
  }

  clearIntegrationMessage(): void {
    this.integrationError.set('');
    this.integrationMessage.set('');
  }

  connectGitHub(event?: MouseEvent): void {
    event?.stopPropagation();
    this.githubConnectLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.recordActivity('Opening the GitHub connection...', 'running');

    this.wizardService.startGitHubOAuth().pipe(
      finalize(() => {
        this.githubConnectLoading.set(false);
        this.showExportMenu.set(false);
      })
    ).subscribe({
      next: (result) => {
        if (result?.authorization_url) {
          const popup = window.open(result.authorization_url, 'github-oauth', 'width=600,height=700,left=200,top=100');
          const cleanup = () => {
            clearInterval(this.oauthPoll);
            window.removeEventListener('message', this.oauthMessageHandler!);
            this.oauthPoll = undefined;
            this.oauthMessageHandler = undefined;
          };
          this.oauthMessageHandler = (e: MessageEvent) => {
            if (e.data === 'github_connected') {
              cleanup();
              this.loadGitHubConnectionStatus();
              this.recordActivity('GitHub account connected successfully.', 'success');
            }
          };
          window.addEventListener('message', this.oauthMessageHandler);
          this.oauthPoll = setInterval(() => {
            if (popup?.closed) {
              cleanup();
              this.loadGitHubConnectionStatus();
            }
          }, 500);
          return;
        }
        console.error('GitHub connection did not return an authorization URL:', result);
        this.recordActivity('GitHub connection could not be started.', 'error');
        this.integrationError.set('Sorry, I could not start the GitHub connection just now. Please try again in a moment.');
      },
      error: (error) => {
        this.recordActivity('GitHub connection could not be started.', 'error');
        this.integrationError.set(this.formatIntegrationError(error, 'Sorry, I could not connect to GitHub just now. Please try again in a moment.'));
      },
    });
  }

  disconnectGitHub(event?: MouseEvent): void {
    event?.stopPropagation();
    this.githubDisconnectLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');

    this.wizardService.disconnectGitHub().pipe(
      finalize(() => this.githubDisconnectLoading.set(false))
    ).subscribe({
      next: () => {
        this.githubConnected.set(false);
        this.githubUsername.set('');
        this.recordActivity('GitHub account disconnected.', 'info');
      },
      error: () => {
        this.integrationError.set('Sorry, I could not disconnect GitHub just now. Please try again in a moment.');
      },
    });
  }

  exportToGitHub(event?: MouseEvent): void {
    event?.stopPropagation();
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      console.error('Cannot export to GitHub because project context is missing.');
      this.integrationError.set('Sorry, I could not find the current project. Please reopen it from the dashboard and try again.');
      this.recordActivity('GitHub sharing could not start because the project was not available.', 'error');
      return;
    }

    if (!this.githubConnected()) {
      this.integrationError.set('Please connect your GitHub account first, then try sharing again.');
      this.recordActivity('GitHub sharing is waiting for account connection.', 'info');
      return;
    }

    this.githubExportLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.showExportMenu.set(false);
    this.recordActivity('Sharing the project with GitHub...', 'running');

    this.wizardService.exportGeneratedCodeToGithub(projectId, sessionId, '', '').pipe(
      finalize(() => {
        this.githubExportLoading.set(false);
      })
    ).subscribe({
      next: (result) => {
        this.integrationMessage.set(result?.pull_request_url
          ? `Your project has been shared with GitHub for review: ${result.pull_request_url}`
          : 'Your project has been shared with GitHub for review.');
        this.recordActivity('GitHub sharing is complete.', 'success');
      },
      error: (error) => {
        this.recordActivity('GitHub sharing could not be completed.', 'error');
        this.integrationError.set(this.formatIntegrationError(error, 'Sorry, I could not share the project with GitHub just now. Please try again in a moment.'));
      },
    });
  }

  createJiraTasks(event?: MouseEvent): void {
    event?.stopPropagation();
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      console.error('Cannot create Jira plan because project context is missing.');
      this.integrationError.set('Sorry, I could not find the current project. Please reopen it from the dashboard and try again.');
      this.recordActivity('Jira plan creation could not start because the project was not available.', 'error');
      return;
    }

    this.jiraTasksLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.showExportMenu.set(false);
    this.recordActivity('Preparing the Jira plan...', 'running');

    this.wizardService.createJiraTasks(projectId, sessionId).pipe(
      finalize(() => {
        this.jiraTasksLoading.set(false);
      })
    ).subscribe({
      next: () => {
        this.integrationMessage.set('Your Jira plan is ready.');
        this.recordActivity('Jira plan is ready.', 'success');
      },
      error: (error) => {
        this.recordActivity('Jira plan creation could not be completed.', 'error');
        this.integrationError.set(this.formatIntegrationError(error, 'Sorry, I could not prepare the Jira plan just now. Please try again in a moment.'));
      },
    });
  }

  exportArtifactsToConfluence(event?: MouseEvent): void {
    event?.stopPropagation();
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      console.error('Cannot export to Confluence because project context is missing.');
      this.integrationError.set('Sorry, I could not find the current project. Please reopen it from the dashboard and try again.');
      this.recordActivity('Document sharing could not start because the project was not available.', 'error');
      return;
    }

    this.confluenceExportLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.showExportMenu.set(false);
    this.recordActivity('Sharing the documents with Confluence...', 'running');

    this.wizardService.exportArtifactsToConfluence(projectId, sessionId, '').pipe(
      finalize(() => {
        this.confluenceExportLoading.set(false);
      })
    ).subscribe({
      next: () => {
        this.integrationMessage.set('Your documents are now available in Confluence.');
        this.recordActivity('Documents have been shared with Confluence.', 'success');
      },
      error: (error) => {
        this.recordActivity('Document sharing could not be completed.', 'error');
        this.integrationError.set(this.formatIntegrationError(error, 'Sorry, I could not share the documents with Confluence just now. Please try again in a moment.'));
      },
    });
  }

  private loadGitHubConnectionStatus(): void {
    this.wizardService.getGitHubConnectionStatus().subscribe({
      next: (result) => {
        this.githubConnected.set(!!result?.connected);
        this.githubUsername.set(result?.github_username || '');
      },
      error: () => {
        this.githubConnected.set(false);
        this.githubUsername.set('');
      },
    });
  }

  private loadAtlassianConnectionStatus(): void {
    this.wizardService.getAtlassianConnectionStatus().subscribe({
      next: (result) => {
        this.atlassianConnected.set(!!result?.connected);
        this.atlassianUsername.set(result?.atlassian_username || '');
      },
      error: () => {
        this.atlassianConnected.set(false);
        this.atlassianUsername.set('');
      },
    });
  }

  connectAtlassian(event?: MouseEvent): void {
    event?.stopPropagation();
    this.atlassianConnectLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.recordActivity('Opening the Atlassian connection...', 'running');

    this.wizardService.startAtlassianOAuth().pipe(
      finalize(() => {
        this.atlassianConnectLoading.set(false);
        this.showExportMenu.set(false);
      })
    ).subscribe({
      next: (result) => {
        if (result?.authorization_url) {
          const popup = window.open(result.authorization_url, 'atlassian-oauth', 'width=600,height=700,left=200,top=100');
          const cleanup = () => {
            clearInterval(this.atlassianOauthPoll);
            if (this.atlassianOauthMessageHandler) window.removeEventListener('message', this.atlassianOauthMessageHandler);
            this.atlassianOauthPoll = undefined;
            this.atlassianOauthMessageHandler = undefined;
          };
          this.atlassianOauthMessageHandler = (e: MessageEvent) => {
            if (e.data === 'atlassian_connected') {
              cleanup();
              this.loadAtlassianConnectionStatus();
              this.recordActivity('Atlassian account connected successfully.', 'success');
            }
          };
          window.addEventListener('message', this.atlassianOauthMessageHandler);
          this.atlassianOauthPoll = setInterval(() => {
            if (popup?.closed) {
              cleanup();
              this.loadAtlassianConnectionStatus();
            }
          }, 500);
          return;
        }
        this.recordActivity('Atlassian connection could not be started.', 'error');
        this.integrationError.set('Sorry, I could not start the Atlassian connection just now. Please try again in a moment.');
      },
      error: (error) => {
        this.recordActivity('Atlassian connection could not be started.', 'error');
        this.integrationError.set(this.formatIntegrationError(error, 'Sorry, I could not connect to Atlassian just now. Please try again in a moment.'));
      },
    });
  }

  disconnectAtlassian(event?: MouseEvent): void {
    event?.stopPropagation();
    this.atlassianDisconnectLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');

    this.wizardService.disconnectAtlassian().pipe(
      finalize(() => this.atlassianDisconnectLoading.set(false))
    ).subscribe({
      next: () => {
        this.atlassianConnected.set(false);
        this.atlassianUsername.set('');
        this.recordActivity('Atlassian account disconnected.', 'info');
      },
      error: () => {
        this.integrationError.set('Sorry, I could not disconnect Atlassian just now. Please try again in a moment.');
      },
    });
  }

  private formatIntegrationError(error: any, fallback: string): string {
    console.error(fallback, error);
    return fallback;
  }

  approveSpec() {
    this.loaderService.startWithMessages(['Reviewing your idea...', 'Organizing the plan...', 'Preparing the next documents...', 'Almost there...']);
    this.recordActivity('Preparing the implementation plan...', 'running');
    this.wizardService.sendMessage('approve').pipe(catchError(err => {
      console.error('Approval request failed:', err);
      this.recordActivity('The implementation plan could not be prepared.', 'error');
      this.integrationError.set('Sorry, I could not prepare the next documents just now. Please try again in a moment.');
      this.loaderService.stop();
      return of(null);
    })).subscribe((reply) => {
      if ((reply as any).technical_artifacts_md) {
        this.specService.setTechnicalArtifacts((reply as any).technical_artifacts_md);
        this.recordActivity('Implementation plan is ready.', 'success');
      }
      this.generateCode();
    });
  }

  showArtifacts() {
    const allFiles: string[] = [];
    const nontechArtifacts = this.specService.nontech_artifacts_md();
    if (nontechArtifacts) allFiles.push(...Object.keys(nontechArtifacts));
    const techArtifacts = this.specService.technical_artifacts_md();
    if (techArtifacts) allFiles.push(...Object.keys(techArtifacts));
    const sortedFiles = this.sortArtifactFiles(allFiles);
    this.files.set(sortedFiles);
    this.selectedFile = sortedFiles[0] || '';
  }

  private sortArtifactFiles(files: string[]): string[] {
    return [...files].sort((a, b) => {
      const indexA = this.artifactOrder.indexOf(a);
      const indexB = this.artifactOrder.indexOf(b);
      if (indexA !== -1 || indexB !== -1) {
        return (indexA === -1 ? Number.MAX_SAFE_INTEGER : indexA) - (indexB === -1 ? Number.MAX_SAFE_INTEGER : indexB);
      }
      return a.localeCompare(b);
    });
  }

  generateCode() {
    this.loaderService.startWithMessages(['Preparing your prototype...', 'Putting the screens together...', 'Adding the main interactions...', 'Almost there...']);
    this.recordActivity('Preparing the interactive prototype...', 'running');
    this.wizardService.sendMessage('generate-code').pipe(catchError(err => {
      console.error('Prototype generation failed:', err);
      this.recordActivity('The prototype could not be prepared.', 'error');
      this.integrationError.set('Sorry, I could not prepare the prototype just now. Please try again in a moment.');
      this.loaderService.stop();
      return of(null);
    })).subscribe((reply) => {
      if ((reply as any).angular_code_files) {
        this.specService.setAngularCode((reply as any).angular_code_files);
        this.files.set([]);
        this.selectedFile = 'code-preview';
        this.loadGitHubConnectionStatus();
        this.loaderService.stop();
        this.recordActivity('Interactive prototype is ready to preview.', 'success');
      } else {
        this.loaderService.stop();
        console.error('Prototype generation did not return preview files:', reply);
        this.recordActivity('The prototype needs a little more work before preview.', 'error');
        this.integrationError.set('The prototype needs a little more work before it is ready to preview. Please try again in a moment.');
      }
    });
  }

  confirmRedeploy() {
    const projectId = this.wizardService.project?.id;
    if (this.specService.deployStatus() === 'running') {
      const confirmed = confirm('Preparing a fresh live demo will replace the current preview link. Continue?');
      if (!confirmed) return;
      if (projectId) {
        this.wizardService.undeployProject(projectId).subscribe({ next: () => {}, error: () => {} });
        this.specService.clearDeploy();
      }
    }
    this.finalizeProject();
  }

  finalizeProject() {
    this.loaderService.startWithMessages(['Preparing the live demo...', 'Connecting the experience...', 'Checking the preview...', 'Almost there...']);
    this.recordActivity('Preparing the live demo setup...', 'running');
    this.wizardService.sendMessage('finalize').pipe(catchError(err => {
      console.error('Live demo preparation failed:', err);
      this.recordActivity('The live demo setup could not be prepared.', 'error');
      this.integrationError.set('Sorry, I could not prepare the live demo just now. Please try again in a moment.');
      this.loaderService.stop();
      return of(null);
    })).subscribe((_) => {
      const projectId = this.wizardService.project?.id;
      if (!projectId) { this.loaderService.stop(); return; }
      this.wizardService.getProject(projectId).subscribe({
        next: (proj) => {
          if (proj.angular_code_files) this.specService.setAngularCode(proj.angular_code_files);
          if (proj.java_code_files) this.specService.setJavaCode(proj.java_code_files);
          this.specService.needsRedeploy.set(!!proj.needs_redeploy);
          this.loaderService.stop();
          this.recordActivity('Live demo setup is ready.', 'success');
        },
        error: (error) => {
          console.error('Failed to refresh project after live demo setup:', error);
          this.loaderService.stop();
          this.recordActivity('The live demo setup could not be refreshed.', 'error');
        },
      });
    });
  }

  private async mmdToSvg(mmdContent: string): Promise<Blob> {
    const mermaidCode = this.extractMermaidCode(mmdContent);
    try {
      mermaid.initialize({ startOnLoad: false, theme: 'default' });
      const id = 'mmd-render-' + Date.now();
      const { svg } = await mermaid.render(id, mermaidCode);
      return new Blob([svg], { type: 'image/svg+xml' });
    } catch {
      return new Blob([this.mermaidSourceToSvg(mermaidCode)], { type: 'image/svg+xml' });
    }
  }

  private extractMermaidCode(content: string): string {
    const codeBlockMatch = content.match(/```mermaid\s*([\s\S]*?)```/);
    const rawCode = codeBlockMatch?.[1] || content;
    return rawCode
      .trim()
      .replace(/ \(/g, ' &lpar;')
      .replace(/\)\)/g, '&rpar;)')
      .replace(/\) /g, '&rpar; ');
  }

  private mermaidSourceToSvg(source: string): string {
    const escapedLines = source
      .split('\n')
      .map(line => this.escapeSvgText(line || ' '))
      .slice(0, 80);
    const lineHeight = 18;
    const height = Math.max(180, 76 + escapedLines.length * lineHeight);
    const textLines = escapedLines
      .map((line, index) => `<text x="24" y="${72 + index * lineHeight}">${line}</text>`)
      .join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="${height}" viewBox="0 0 1200 ${height}">
  <rect width="1200" height="${height}" fill="#f8fafc"/>
  <rect x="16" y="16" width="1168" height="${height - 32}" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
  <text x="24" y="42" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#0f172a">Mermaid source could not be rendered</text>
  <g font-family="Courier New, monospace" font-size="13" fill="#334155">${textLines}</g>
</svg>`;
  }

  private escapeSvgText(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async downloadZip(event?: MouseEvent) {
    event?.stopPropagation();
    this.showExportMenu.set(false);

    const stale = this.specService.needsRedeploy();
    const running = this.specService.deployStatus() === 'running';
    if (stale || running) {
      let msg: string;
      if (stale && running) {
        msg = 'Your latest changes are not included in the current live demo yet. You can prepare a fresh live demo first, or download the current version now. Download anyway?';
      } else if (stale) {
        msg = 'Your latest changes are not included in the live demo package yet. You can prepare a fresh live demo first, or download the current version now. Download anyway?';
      } else {
        msg = 'The current preview link will be closed after download. Continue?';
      }
      const confirmed = confirm(msg);
      if (!confirmed) return;
      if (running) {
        const projectId = this.wizardService.project?.id;
        if (projectId) {
          await new Promise<void>(resolve => {
            this.wizardService.undeployProject(projectId).subscribe({ next: () => resolve(), error: () => resolve() });
          });
          this.specService.clearDeploy();
        }
      }
    }
    this.recordActivity('Preparing the project download...', 'running');
    try {
    const angularFiles = this.specService.angular_code_files();
    const javaFiles = this.specService.java_code_files();
    const nontechArtifacts = this.specService.nontech_artifacts_md();
    const technicalArtifacts = this.specService.technical_artifacts_md();
    const zip = new JSZip();

    if (angularFiles) {
      const fe = zip.folder('frontend')!;
      Object.entries(angularFiles).forEach(([path, content]) => fe.file(path, content));
    }
    if (javaFiles) {
      const be = zip.folder('backend')!;
      Object.entries(javaFiles).forEach(([path, content]) => be.file(path, content));
    }

    const allArtifacts = { ...nontechArtifacts, ...technicalArtifacts };
    if (Object.keys(allArtifacts).length > 0) {
      const af = zip.folder('artifacts')!;
      for (const [filename, content] of Object.entries(allArtifacts)) {
        if (filename.toLowerCase().endsWith('.mmd')) {
          const svg = await this.mmdToSvg(content);
          af.file(filename.replace(/\.mmd$/i, '.svg'), svg);
        } else {
          af.file(filename, content);
        }
      }
    }

    const blob = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const rawName = this.wizardService.project?.title || this.wizardService.project?.id || 'project';
    const safeName = rawName.replace(/[^a-zA-Z0-9一-鿿_-]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '');
    a.download = `${safeName}.zip`;
    a.click();
    URL.revokeObjectURL(url);
    this.recordActivity('Project download is ready.', 'success');
    } catch (e) {
      console.error('Download failed:', e);
      this.recordActivity('Project download could not be prepared.', 'error');
      alert('Sorry, I could not prepare the download just now. Please try again in a moment.');
    }
  }

  ngOnDestroy() {
    this.pollSub?.unsubscribe();
    clearInterval(this.oauthPoll);
    if (this.oauthMessageHandler) window.removeEventListener('message', this.oauthMessageHandler);
    clearInterval(this.atlassianOauthPoll);
    if (this.atlassianOauthMessageHandler) window.removeEventListener('message', this.atlassianOauthMessageHandler);
  }

  deployProject() {
    const projectId = this.wizardService.project?.id;
    if (!projectId) return;

    this.specService.setDeployStatus('building');
    this.recordActivity('Creating the live demo link...', 'running');
    this.wizardService.deployProject(projectId).pipe(
      catchError((error) => {
        console.error('Live demo creation failed:', error);
        this.specService.setDeployStatus('failed');
        this.recordActivity('The live demo link could not be created.', 'error');
        return of(null);
      })
    ).subscribe(res => {
      if (!res) return;
      this.pollSub = interval(3000).pipe(
        switchMap(() => this.wizardService.getDeployStatus(projectId)),
        takeWhile(s => s.status === 'building', true),
        catchError(() => of({ status: 'failed', url: null }))
      ).subscribe(s => {
        if (s.status === 'running') {
          this.specService.setDeployStatus('running', s.url);
          this.recordActivity('Live demo link is ready.', 'success');
        } else if (s.status === 'failed') {
          this.specService.setDeployStatus('failed');
          this.recordActivity('The live demo link could not be created.', 'error');
        }
      });
    });
  }

  openStaleDeployLink(): void {
    const confirmed = confirm(
      'This preview link is from an earlier version. Prepare a fresh live demo to include your latest changes. Open the older preview anyway?'
    );
    if (confirmed) {
      window.open(this.specService.deployUrl()!, '_blank', 'noopener');
    }
  }

  viewPrototype() {
    this.selectedFile = 'code-preview';
  }

  onFileSelect(file: string) {
    this.selectedFile = file;
  }

  getMdText(file: string): string {
    const nontechArtifacts = this.specService.nontech_artifacts_md();
    if (nontechArtifacts && nontechArtifacts[file]) {
      return nontechArtifacts[file];
    }
    const technicalArtifacts = this.specService.technical_artifacts_md();
    if (technicalArtifacts && technicalArtifacts[file]) {
      return technicalArtifacts[file];
    }
    return `# ${file}\n\nContent not found for this file.`;
  }

}
