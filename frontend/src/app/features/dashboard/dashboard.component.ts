import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { WizardService } from '../../features/requirements/services/wizard-service';
import { AuthService } from '../../core/auth.service';
import { ProjectCard } from '../../shared/models/project-card.model';
import { HeaderComponent } from '../../shared/components/header/header.component';
import { SpecService } from '../spec-review/services/spec.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, HeaderComponent, FormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  projects = signal<ProjectCard[]>([]);
  isLoading = signal(false);
  currentUser = signal<string | null>(null);
  showCreateForm = signal(false);
  projectTitle = '';
  projectDescription = '';

  private wizardService = inject(WizardService);
  private authService = inject(AuthService);
  private router = inject(Router);
  private specService = inject(SpecService);

  ngOnInit(): void {
    this.currentUser.set(this.authService.getCurrentUser()()?.username || '');
    this.loadProjects();
  }

  loadProjects(): void {
    this.isLoading.set(true);
    this.wizardService.getProjects().subscribe({
      next: (res) => {
        this.projects.set((res.projects || []) as ProjectCard[]);
        this.isLoading.set(false);
      },
      error: (err) => {
        console.error('Failed to load projects:', err);
        this.isLoading.set(false);
      },
    });
  }

  onCreateNew(): void {
    this.showCreateForm.set(true)
  }

  onProjectClick(project: ProjectCard): void {
    // Navigate based on stage
    const stage = project.stage;
    const stageToRouteMap: { [key: string]: string } = {
      REQ: '/requirements',
      ARTIFACTS_NON_TECH: '/spec-review',
      WAIT_APPROVAL: '/spec-review',
      TECH_ARTIFACTS: '/spec-review',
      CODEGEN: '/spec-review',
      QA: '/spec-review',
    };

    const route = stageToRouteMap[stage] || '/requirements';
    
    // Load project first, then navigate
    this.wizardService.getProject(project.project_id).subscribe({
      next: (proj) => {
        this.wizardService.loadExistingProject(proj);
        
        // Set spec and artifacts data
        if (proj.spec) {
          this.specService.setSpec(proj.spec);
        }
        if (proj.nontech_artifacts_md) {
          this.specService.setNontechArtifacts(proj.nontech_artifacts_md);
        }
        if (proj.technical_artifacts_md) {
          this.specService.setTechnicalArtifacts(proj.technical_artifacts_md);
        }
        if (proj.generated_code_files) {
          this.specService.setGeneratedCode(proj.generated_code_files);
        }
        
        this.router.navigate([route]);
      },
      error: (err) => {
        console.error('Failed to load project:', err);
      },
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/welcome']);
  }

  formatDate(dateString: string): string {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateString;
    }
  }

  getStageLabel(stage: string): string {
    const stageLabels: { [key: string]: string } = {
      REQ: 'Requirements',
      ARTIFACTS_NON_TECH: 'Non-Tech Artifacts',
      WAIT_APPROVAL: 'Awaiting Approval',
      TECH_ARTIFACTS: 'Technical Artifacts',
      CODEGEN: 'Code Generation',
      QA: 'QA',
    };
    return stageLabels[stage] || stage;
  }

confirmCreateProject(): void {
  const userId = this.currentUser() || 'local-user';

  if (!this.projectTitle.trim()) {
    alert('Please enter a project title.');
    return;
  }

  this.wizardService.resetSession();
  this.specService.clearSpec();
  this.specService.clearArtifacts();
  this.specService.clearGeneratedCode();

  this.wizardService.createProject(
    userId,
    this.projectTitle.trim(),
    this.projectDescription.trim()
  );

  this.wizardService.createProjectInDb().subscribe({
    next: (res) => {
      console.log('Project saved to database:', res);
      this.router.navigate(['/requirements']);
    },
    error: (err) => {
      console.error('Failed to create project in database:', err);
      alert('Failed to create project. Please try again.');
    },
  });
}

  cancelCreateProject(): void {
    this.showCreateForm.set(false);
    this.projectTitle = '';
    this.projectDescription = '';
  }
}
