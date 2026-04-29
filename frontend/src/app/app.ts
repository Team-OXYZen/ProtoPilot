import { Component, inject, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { WizardComponent } from './features/requirements/components/wizard/wizard';
import { ReviewWrapperComponent } from './features/spec-review/review-wrapper';
import { SpecService } from './features/spec-review/services/spec.service';
import { LoaderComponent } from './shared/components/loader/loader.component';
import { WizardService } from './features/requirements/services/wizard-service';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterOutlet, WizardComponent, ReviewWrapperComponent, LoaderComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit {
  currentView: 'wizard' | 'review' = 'wizard';

  projects: any[] = [];
  selectedProjectId = '';

  private specService = inject(SpecService);
  private wizardService = inject(WizardService);

  ngOnInit(): void {
    this.loadProjectList();
  }

  loadProjectList(): void {
    this.wizardService.getProjects().subscribe({
      next: (res) => {
        this.projects = res.projects || [];
      },
      error: (err) => {
        console.error('Failed to load projects:', err);
      }
    });
  }

  loadProject(projectId: string): void {
    if (!projectId) return;

    this.wizardService.getProject(projectId).subscribe({
      next: (project) => {
        this.wizardService.loadExistingProject(project);

        this.specService.setSpec(project.spec || {});
        this.specService.setNontechArtifacts(project.nontech_artifacts_md || {});
        this.specService.setTechnicalArtifacts(project.technical_artifacts_md || {});
        this.specService.setGeneratedCode(project.generated_code_files || {});

        this.currentView = 'review';

        console.log('Project loaded:', project);
      },
      error: (err) => {
        console.error('Failed to load project:', err);
      }
    });
  }

  onWizardComplete(data: any) {
    this.specService.setSpec(data.spec);

    if (data.nontech_artifacts_md) {
      this.specService.setNontechArtifacts(data.nontech_artifacts_md);
    }

    if (data.technical_artifacts_md) {
      this.specService.setTechnicalArtifacts(data.technical_artifacts_md);
    }

    this.loadProjectList();
    this.currentView = 'review';
  }
}