import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { WizardService } from '../../features/requirements/services/wizard-service';
import { AuthService } from '../../core/auth.service';
import { ProjectCard } from '../../shared/models/project-card.model';
import { HeaderComponent } from '../../shared/components/header/header.component';
import { SpecService } from '../spec-review/services/spec.service';

type PreferenceRow = {
  key: string;
  label: string;
  value: string;
  secret?: boolean;
  placeholder?: string;
};

const CONFIG_FIELDS: Omit<PreferenceRow, 'value'>[] = [
  { key: 'GITHUB_CLIENT_ID', label: 'GitHub OAuth client ID', secret: true },
  { key: 'GITHUB_CLIENT_SECRET', label: 'GitHub OAuth client secret', secret: true },
  { key: 'GITHUB_OWNER', label: 'GitHub owner or organization' },
  { key: 'GITHUB_REPO', label: 'GitHub repository' },
  { key: 'ATLASSIAN_CLIENT_ID', label: 'Atlassian OAuth client ID', secret: true },
  { key: 'ATLASSIAN_CLIENT_SECRET', label: 'Atlassian OAuth client secret', secret: true },
  { key: 'JIRA_PROJECT_KEY', label: 'Jira project key', placeholder: 'e.g. PROTO' },
  { key: 'CONFLUENCE_SPACE_KEY', label: 'Confluence space key', placeholder: 'e.g. PROTO' },
  { key: 'CONFLUENCE_PARENT_PAGE_TITLE', label: 'Confluence parent page title' },
];

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
  showPreferences = signal(false);
  preferencesLoading = signal(false);
  preferencesSaving = signal(false);
  preferencesError = signal('');
  preferencesMessage = signal('');
  preferenceRows: PreferenceRow[] = [];
  editingProject = signal<ProjectCard | null>(null);
  editTitle = '';
  editDescription = '';

  private wizardService = inject(WizardService);
  private authService = inject(AuthService);
  private router = inject(Router);
  private specService = inject(SpecService);

  ngOnInit(): void {
    const username = this.authService.getCurrentUser()()?.username || '';
    this.currentUser.set(username);

    if (!username || !this.authService.getToken()) {
      this.router.navigate(['/welcome']);
      return;
    }

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
    this.editingProject.set(null);
    this.editTitle = '';
    this.editDescription = '';
    this.showCreateForm.set(true);
  }

  openPreferences(): void {
    this.showPreferences.set(true);
    this.preferencesError.set('');
    this.preferencesMessage.set('');
    this.preferencesLoading.set(true);

    this.wizardService.getUserPreferences().subscribe({
      next: (res) => {
        const preferences = res.preferences || {};
        this.preferenceRows = this.buildPreferenceRows(preferences);
        this.preferencesLoading.set(false);
      },
      error: (err) => {
        console.error('Failed to load preferences:', err);
        this.preferencesError.set('Failed to load preferences.');
        this.preferenceRows = this.buildPreferenceRows({});
        this.preferencesLoading.set(false);
      },
    });
  }

  closePreferences(): void {
    this.showPreferences.set(false);
    this.preferencesError.set('');
    this.preferencesMessage.set('');
  }

  private buildPreferenceRows(preferences: Record<string, string>): PreferenceRow[] {
    return CONFIG_FIELDS.map((field) => ({
      ...field,
      value: preferences[field.key] || '',
    }));
  }

  savePreferences(): void {
    const preferences: Record<string, string> = {};
    this.preferencesError.set('');
    this.preferencesMessage.set('');

    for (const row of this.preferenceRows) {
      const key = row.key;
      const value = row.value.trim();
      if (!value && !row.secret) {
        continue;
      }
      preferences[key] = value;
    }

    this.preferencesSaving.set(true);
    this.wizardService.saveUserPreferences(preferences).subscribe({
      next: (res) => {
        this.preferenceRows = this.buildPreferenceRows(res.preferences || {});
        this.preferencesMessage.set('Settings saved.');
        this.preferencesSaving.set(false);
      },
      error: (err) => {
        this.preferencesError.set(err?.error?.detail || 'Failed to save preferences.');
        this.preferencesSaving.set(false);
      },
    });
  }

  onProjectClick(project: ProjectCard): void {
    this.wizardService.resetSession();
    this.specService.clearSpec();
    this.specService.clearArtifacts();
    this.specService.clearGeneratedCode();
    this.specService.clearDeploy();

    // Navigate based on stage
    const stage = project.stage;
    const stageToRouteMap: { [key: string]: string } = {
      REQ: '/requirements',
      ARTIFACTS_NON_TECH: '/spec-review',
      WAIT_APPROVAL: '/spec-review',
      TECH_ARTIFACTS: '/spec-review',
      CODEGEN: '/spec-review',
      QA: '/spec-review',
      FINALIZE: '/spec-review',
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
        if (proj.angular_code_files) {
          this.specService.setAngularCode(proj.angular_code_files);
        }
        if (proj.java_code_files) {
          this.specService.setJavaCode(proj.java_code_files);
        }
        this.specService.needsRedeploy.set(!!proj.needs_redeploy);

        this.router.navigate([route]);
      },
      error: (err) => {
        console.error('Failed to load project:', err);
      },
    });
  }

  onEditProject(event: MouseEvent, project: ProjectCard): void {
    event.stopPropagation();
    this.showCreateForm.set(false);
    this.editTitle = project.project_title || '';
    this.editDescription = project.project_description || '';
    this.editingProject.set(project);
  }

  confirmEditProject(): void {
    const project = this.editingProject();
    if (!project || !this.editTitle.trim()) return;

    this.wizardService.updateProject(project.project_id, this.editTitle.trim(), this.editDescription.trim()).subscribe({
      next: () => {
        this.projects.update(list => list.map(p =>
          p.project_id === project.project_id
            ? { ...p, project_title: this.editTitle.trim(), project_description: this.editDescription.trim() }
            : p
        ));
        this.closeProjectModal();
      },
      error: (err) => {
        console.error('Failed to update project:', err);
        alert('Failed to update project. Please try again.');
      },
    });
  }

  cancelEditProject(): void {
    this.editingProject.set(null);
    this.editTitle = '';
    this.editDescription = '';
  }

  closeProjectModal(): void {
    this.showCreateForm.set(false);
    this.editingProject.set(null);
    this.editTitle = '';
    this.editDescription = '';
  }

  onDeleteProject(event: MouseEvent, project: ProjectCard): void {
    event.stopPropagation();
    if (!confirm(`Delete "${project.project_title || project.project_id}"? This cannot be undone.`)) return;

    this.wizardService.deleteProject(project.project_id).subscribe({
      next: () => {
        this.projects.update(list => list.filter(p => p.project_id !== project.project_id));
      },
      error: (err) => {
        console.error('Failed to delete project:', err);
        alert('Failed to delete project. Please try again.');
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
      REQ: 'Gathering Ideas',
      ARTIFACTS_NON_TECH: 'Preparing Documents',
      WAIT_APPROVAL: 'Ready for Review',
      TECH_ARTIFACTS: 'Planning Prototype',
      CODEGEN: 'Building Prototype',
      QA: 'Ready to Preview',
      FINALIZE: 'Preparing Live Demo',
    };
    return stageLabels[stage] || 'In Progress';
  }

  confirmCreateProject(): void {
    const userId = this.currentUser();

    if (!userId) {
      alert('You must be logged in to create a project.');
      return;
    }

    if (!this.editTitle.trim()) {
      alert('Please enter a project title.');
      return;
    }

    this.wizardService.resetSession();
    this.specService.clearSpec();
    this.specService.clearArtifacts();
    this.specService.clearGeneratedCode();
    this.specService.clearDeploy();

    this.wizardService.createProject(
      userId,
      this.editTitle.trim(),
      this.editDescription.trim()
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
    this.closeProjectModal();
  }
}
