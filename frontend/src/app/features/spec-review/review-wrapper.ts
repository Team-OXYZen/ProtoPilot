import { Component, effect, HostListener, inject, OnDestroy, OnInit, signal, ViewChild } from '@angular/core';
import { Router } from '@angular/router';
import JSZip from 'jszip';
import { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType } from 'docx';
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
  githubConnected = signal(false);
  githubUsername = signal('');
  jiraTasksLoading = signal(false);
  confluenceExportLoading = signal(false);
  integrationError = signal('');
  integrationMessage = signal('');

  private pollSub?: Subscription;

  wizardService = inject(WizardService);
  specService = inject(SpecService);
  loaderService = inject(LoaderService);
  router = inject(Router);

  constructor() {
    // Auto-refresh file list when non-tech artifacts change (e.g. after chatbox modification)
    effect(() => {
      const nontechArtifacts = this.specService.nontech_artifacts_md();
      const technicalArtifacts = this.specService.technical_artifacts_md();

      if (nontechArtifacts && this.selectedFile !== 'code-preview') {
        const allFiles = Object.keys(nontechArtifacts).sort();

        if (technicalArtifacts) {
          allFiles.push(...Object.keys(technicalArtifacts).sort());
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
      const allFiles = Object.keys(this.specService.nontech_artifacts_md() as any).sort();
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
    if (this.hasGeneratedCode()) {
      this.loadGitHubConnectionStatus();
    }
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

  connectGitHub(event?: MouseEvent): void {
    event?.stopPropagation();
    this.githubConnectLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');

    this.wizardService.startGitHubOAuth().pipe(
      finalize(() => {
        this.githubConnectLoading.set(false);
        this.showExportMenu.set(false);
      })
    ).subscribe({
      next: (result) => {
        if (result?.authorization_url) {
          window.location.href = result.authorization_url;
          return;
        }
        this.integrationError.set('GitHub authorization URL was not returned.');
      },
      error: (error) => {
        this.integrationError.set(this.formatIntegrationError(error, 'GitHub connection failed.'));
      },
    });
  }

  exportToGitHub(event?: MouseEvent): void {
    event?.stopPropagation();
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      this.integrationError.set('Missing project or session id.');
      return;
    }

    if (!this.githubConnected()) {
      this.integrationError.set('Connect your GitHub account before exporting.');
      return;
    }

    this.githubExportLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.showExportMenu.set(false);

    this.wizardService.exportGeneratedCodeToGithub(projectId, sessionId, '', '').pipe(
      finalize(() => {
        this.githubExportLoading.set(false);
      })
    ).subscribe({
      next: (result) => {
        this.integrationMessage.set(result?.pull_request_url
          ? `GitHub export complete: ${result.pull_request_url}`
          : 'GitHub export complete.');
      },
      error: (error) => {
        this.integrationError.set(this.formatIntegrationError(error, 'GitHub export failed.'));
      },
    });
  }

  createJiraTasks(event?: MouseEvent): void {
    event?.stopPropagation();
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      this.integrationError.set('Missing project or session id.');
      return;
    }

    this.jiraTasksLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.showExportMenu.set(false);

    this.wizardService.createJiraTasks(projectId, sessionId).pipe(
      finalize(() => {
        this.jiraTasksLoading.set(false);
      })
    ).subscribe({
      next: () => {
        this.integrationMessage.set('Jira product plan creation requested.');
      },
      error: (error) => {
        this.integrationError.set(this.formatIntegrationError(error, 'Jira product plan creation failed.'));
      },
    });
  }

  exportArtifactsToConfluence(event?: MouseEvent): void {
    event?.stopPropagation();
    const projectId = this.wizardService.project?.id;
    const sessionId = this.wizardService.session?.id;

    if (!projectId || !sessionId) {
      this.integrationError.set('Missing project or session id.');
      return;
    }

    this.confluenceExportLoading.set(true);
    this.integrationError.set('');
    this.integrationMessage.set('');
    this.showExportMenu.set(false);

    this.wizardService.exportArtifactsToConfluence(projectId, sessionId, '').pipe(
      finalize(() => {
        this.confluenceExportLoading.set(false);
      })
    ).subscribe({
      next: () => {
        this.integrationMessage.set('Confluence artifact export requested.');
      },
      error: (error) => {
        this.integrationError.set(this.formatIntegrationError(error, 'Confluence artifact export failed.'));
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

  private formatIntegrationError(error: any, fallback: string): string {
    return error?.error?.detail || error?.message || fallback;
  }

  approveSpec() {
    this.loaderService.startWithMessages(['Understanding requirements...', 'Analyzing...', 'Generating system design...', 'Generating API documentation...', 'Almost there...']);
    this.wizardService.sendMessage('approve').pipe(catchError(err => {
      console.log('Error caught:', err);
      this.loaderService.stop();
      return of(null);
    })).subscribe((reply) => {
      if ((reply as any).technical_artifacts_md) {
        this.specService.setTechnicalArtifacts((reply as any).technical_artifacts_md);
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
    this.files.set(allFiles.sort());
    this.selectedFile = allFiles[0] || '';
  }

  generateCode() {
    this.loaderService.startWithMessages(['Generating code...', 'Building components...', 'Wiring up services...', 'Almost there...']);
    this.wizardService.sendMessage('generate-code').pipe(catchError(err => {
      console.log('Error caught:', err);
      this.loaderService.stop();
      return of(null);
    })).subscribe((reply) => {
      if ((reply as any).angular_code_files) {
        this.specService.setAngularCode((reply as any).angular_code_files);
        this.files.set([]);
        this.selectedFile = 'code-preview';
        this.loadGitHubConnectionStatus();
        this.loaderService.stop();
      } else {
        this.loaderService.stop();
        console.error('Code generation failed');
      }
    });
  }

  confirmRedeploy() {
    const projectId = this.wizardService.project?.id;
    if (this.specService.deployStatus() === 'running') {
      const confirmed = confirm('Re-finalizing will regenerate the backend and stop the current deployment link. Continue?');
      if (!confirmed) return;
      if (projectId) {
        this.wizardService.undeployProject(projectId).subscribe({ next: () => {}, error: () => {} });
        this.specService.clearDeploy();
      }
    }
    this.finalizeProject();
  }

  finalizeProject() {
    this.loaderService.startWithMessages(['Analysing Angular services...', 'Generating Spring Boot code...', 'Updating Angular services...', 'Almost there...']);
    this.wizardService.sendMessage('finalize').pipe(catchError(err => {
      console.log('Error caught:', err);
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
        },
        error: () => this.loaderService.stop(),
      });
    });
  }

  private async mmdToSvg(mmdContent: string): Promise<Blob | null> {
    try {
      mermaid.initialize({ startOnLoad: false, theme: 'default' });
      const id = 'mmd-render-' + Date.now();
      const { svg } = await mermaid.render(id, mmdContent);
      return new Blob([svg], { type: 'image/svg+xml' });
    } catch {
      return null;
    }
  }

  private parseInlineRuns(text: string, forceBold = false): TextRun[] {
    const runs: TextRun[] = [];
    const segments = text.split(/<br\s*\/?>/gi);
    segments.forEach((segment, idx) => {
      if (idx > 0) runs.push(new TextRun({ break: 1 }));
      for (const part of segment.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)) {
        if (part.startsWith('**') && part.endsWith('**')) {
          runs.push(new TextRun({ text: part.slice(2, -2), bold: true }));
        } else if (part.startsWith('*') && part.endsWith('*')) {
          runs.push(new TextRun({ text: part.slice(1, -1), italics: !forceBold, bold: forceBold }));
        } else if (part.startsWith('`') && part.endsWith('`')) {
          runs.push(new TextRun({ text: part.slice(1, -1), bold: forceBold, font: { name: 'Courier New' } }));
        } else {
          runs.push(new TextRun({ text: part, bold: forceBold || undefined }));
        }
      }
    });
    return runs;
  }

  private mdToDocxParagraphs(md: string): (Paragraph | Table)[] {
    const elements: (Paragraph | Table)[] = [];
    const lines = md.split('\n');
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // markdown table: collect consecutive | lines
      if (line.startsWith('|')) {
        const tableLines: string[] = [];
        while (i < lines.length && lines[i].startsWith('|')) {
          tableLines.push(lines[i]);
          i++;
        }
        const dataRows = tableLines.filter(r => !/^\|[\s|:\-]+\|$/.test(r.trim()));
        if (dataRows.length > 0) {
          elements.push(new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: dataRows.map((row, rowIdx) => new TableRow({
              children: row.split('|').slice(1, -1).map(cell => new TableCell({
                children: [new Paragraph({ children: this.parseInlineRuns(cell.trim(), rowIdx === 0) })],
                shading: rowIdx === 0 ? { type: ShadingType.SOLID, color: 'D9D9D9' } : undefined,
              })),
            })),
          }));
          elements.push(new Paragraph({}));
        }
        continue;
      }

      if (/^-{3,}$/.test(line.trim())) {
        elements.push(new Paragraph({}));
      } else if (line.startsWith('### ')) {
        elements.push(new Paragraph({ text: line.slice(4), heading: HeadingLevel.HEADING_3 }));
      } else if (line.startsWith('## ')) {
        elements.push(new Paragraph({ text: line.slice(3), heading: HeadingLevel.HEADING_2 }));
      } else if (line.startsWith('# ')) {
        elements.push(new Paragraph({ text: line.slice(2), heading: HeadingLevel.HEADING_1 }));
      } else if (line.startsWith('- ') || line.startsWith('* ')) {
        elements.push(new Paragraph({ children: this.parseInlineRuns(line.slice(2)), bullet: { level: 0 } }));
      } else if (line.startsWith('> ')) {
        elements.push(new Paragraph({ children: this.parseInlineRuns(line.slice(2)), indent: { left: 720 } }));
      } else if (line.trim() === '') {
        elements.push(new Paragraph({}));
      } else {
        elements.push(new Paragraph({ children: this.parseInlineRuns(line), alignment: AlignmentType.LEFT }));
      }
      i++;
    }
    return elements;
  }

  async downloadZip(event?: MouseEvent) {
    event?.stopPropagation();
    this.showExportMenu.set(false);

    const stale = this.specService.needsRedeploy();
    const running = this.specService.deployStatus() === 'running';
    if (stale || running) {
      let msg: string;
      if (stale && running) {
        msg = 'The backend code is not up to date with your latest changes — re-finalize first if you want the latest version. The current preview link will also be closed. Download anyway?';
      } else if (stale) {
        msg = 'The backend code is not up to date with your latest changes. Re-finalize first if you want to download the latest version. Download anyway?';
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
        if (filename.endsWith('.mmd')) {
          const svg = await this.mmdToSvg(content);
          if (svg) {
            af.file(filename.replace(/\.mmd$/, '.svg'), svg);
          } else {
            af.file(filename, content);
          }
        } else {
          const doc = new Document({ sections: [{ children: this.mdToDocxParagraphs(content) }] });
          af.file(filename.replace(/\.md$/, '.docx'), await Packer.toBlob(doc));
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
    } catch (e) {
      alert('Download failed: ' + e);
    }
  }

  ngOnDestroy() {
    this.pollSub?.unsubscribe();
  }

  deployProject() {
    const projectId = this.wizardService.project?.id;
    if (!projectId) return;

    this.specService.setDeployStatus('building');
    this.wizardService.deployProject(projectId).pipe(
      catchError(() => { this.specService.setDeployStatus('failed'); return of(null); })
    ).subscribe(res => {
      if (!res) return;
      this.pollSub = interval(3000).pipe(
        switchMap(() => this.wizardService.getDeployStatus(projectId)),
        takeWhile(s => s.status === 'building', true),
        catchError(() => of({ status: 'failed', url: null }))
      ).subscribe(s => {
        if (s.status === 'running') this.specService.setDeployStatus('running', s.url);
        else if (s.status === 'failed') this.specService.setDeployStatus('failed');
      });
    });
  }

  openStaleDeployLink(): void {
    const confirmed = confirm(
      'This preview link is from a previous version. Re-finalize the project and re-deploy to sync the backend with your latest changes. Open the outdated link anyway?'
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
