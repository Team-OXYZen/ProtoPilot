import { Component, effect, inject, OnInit, signal, ViewChild } from '@angular/core';
import { LeftPanelComponent } from './left-panel';
import { RightPanelComponent } from './right-panel';
import { WizardService } from '../requirements/services/wizard-service';
import { SpecService } from './services/spec.service';
import { catchError, of } from 'rxjs';
import { ChatboxComponent } from './chatbox';
import { LoaderService } from '../../shared/services/loader.service';
import { ThemeToggleComponent } from '../../shared/components/theme-toggle/theme-toggle.component';


@Component({
  selector: 'app-review-wrapper',
  standalone: true,
  imports: [LeftPanelComponent, RightPanelComponent, ChatboxComponent, ThemeToggleComponent],
  templateUrl: './review-wrapper.html',
  styleUrl: './review-wrapper.scss'
})
export class ReviewWrapperComponent implements OnInit {

  @ViewChild(ChatboxComponent) chatbox!: ChatboxComponent;

  selectedFile: string = 'requirements.md';
  files = signal<string[]>([]);

  wizardService = inject(WizardService);
  specService = inject(SpecService);
  loaderService = inject(LoaderService);

  constructor() {
    // Auto-refresh file list when non-tech artifacts change (e.g. after chatbox modification)
    effect(() => {
      const nontechArtifacts = this.specService.nontech_artifacts_md();
      if (nontechArtifacts && this.selectedFile !== 'code-preview') {
        const allFiles = Object.keys(nontechArtifacts).sort();
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
    return this.specService.generated_code_files() && Object.keys(this.specService.generated_code_files() as any).length > 0;
  }

  ngOnInit() {
    if (this.hasNonTechArtifacts()) {
      const allFiles = Object.keys(this.specService.nontech_artifacts_md() as any).sort();
      this.files.set(allFiles);
      this.selectedFile = allFiles[0] || 'requirements.md';
    }
    if (this.hasGeneratedCode()) {
      this.selectedFile = 'code-preview';
    }
  }

  isStackblitzActive() {
    return this.selectedFile === 'code-preview';
  }

  approveSpec() {
    this.loaderService.startWithMessages(['Approving...', 'Generating technical artifacts...', 'Almost there...']);
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

  changeSpec() {
    this.chatbox.focusInput();
  }

  showArtifacts() {
    const allFiles: string[] = [];
    const nontechArtifacts = this.specService.nontech_artifacts_md();
    if (nontechArtifacts) allFiles.push(...Object.keys(nontechArtifacts));
    const techArtifacts = this.specService.technical_artifacts_md();
    if (techArtifacts) allFiles.push(...Object.keys(techArtifacts));
    this.files.set(allFiles.sort());
    this.selectedFile = allFiles[0] || 'requirements.md';
  }

  generateCode() {
    this.loaderService.startWithMessages(['Generating code...', 'Building components...', 'Wiring up services...', 'Almost there...']);
    this.wizardService.sendMessage('generate-code').pipe(catchError(err => {
      console.log('Error caught:', err);
      this.loaderService.stop();
      return of(null);
    })).subscribe((reply) => {
      if ((reply as any).generated_code_files) {
        this.specService.setGeneratedCode((reply as any).generated_code_files);
        this.files.set([]);
        this.selectedFile = 'code-preview';
        this.loaderService.stop();
      } else {
        this.loaderService.stop();
        console.error('Code generation failed');
      }
    });
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
