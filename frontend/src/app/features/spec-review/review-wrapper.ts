import { Component, inject, OnInit, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { LeftPanelComponent } from './left-panel';
import { RightPanelComponent } from './right-panel';
import { WizardService } from '../requirements/services/wizard-service';
import { SpecService } from './services/spec.service';
import { catchError, of } from 'rxjs';
import { ChatboxComponent } from './chatbox';
import { LivePreviewComponent } from './components/live-preview/live-preview.component';
import { LoaderService } from '../../shared/services/loader.service';


@Component({
  selector: 'app-review-wrapper',
  standalone: true,
  imports: [LeftPanelComponent, RightPanelComponent, ChatboxComponent],
  templateUrl: './review-wrapper.html',
  styleUrl: './review-wrapper.css'
})
export class ReviewWrapperComponent implements OnInit {

  selectedSection: string = '';
  isPreviewMode = signal(false);
  selectedFile: string = 'requirements.md';
  files = signal<string[]>([]);

  http = inject(HttpClient);
  wizardService = inject(WizardService);
  specService = inject(SpecService);
  loaderService = inject(LoaderService);

  get spec() {
    return this.specService.spec();
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
    if (Object.keys(this.spec).length === 0) {
      this.http.get('/assets/temp_reqs.json').subscribe({
        next: (data) => {
          this.specService.setSpec(data);
          this.selectedSection = Object.keys(this.specService.spec()).sort()[0];
        },
        error: () => {
          this.specService.setSpec(this.tempReqs);
          this.selectedSection = Object.keys(this.specService.spec()).sort()[0];
        }
      });
    } else {
      this.selectedSection = Object.keys(this.spec).sort()[0];
    }
  }

  tempReqs = {
    "project_name": "Simple To-Do App",
    "functional_requirements": [
      {
        "description": "Users can add a new task with a title and a description.",
        "name": "Create Task"
      },
      {
        "name": "View Task List",
        "description": "All tasks are displayed in a list."
      },
      {
        "description": "Users can mark a task as completed. Completed tasks should be visually differentiated from active tasks.",
        "name": "Mark Task as Complete"
      }
    ],
    "non_goals": [
      "Team collaboration features.",
      "User accounts and authentication.",
      "Advanced features like sub-tasks, reminders, or attachments."
    ],
    "goals": [
      "Enable users to quickly add tasks.",
      "Allow users to view all their tasks in a list.",
      "Provide a way for users to mark tasks as complete."
    ],
    "non_functional_requirements": {
      "performance": "The application should load quickly and provide instant feedback for user actions.",
      "scalability": "Not a primary concern for a personal task management application.",
      "security": "As a simple client-side application, security will be limited to standard web practices. No sensitive user data is stored.",
      "availability": "The application should be accessible at all times."
    },
    "assumptions": [
      "The application will be a single-page web application.",
      "Task data will be stored in the browser's local storage.",
      "The user interface will be minimalist and intuitive."
    ],
    "target_users": [
      "Individuals seeking a personal task management tool"
    ],
    "open_questions": [
      "Should users be able to edit tasks after creation?",
      "Should users be able to delete tasks?",
      "How should the task list be sorted?"
    ],
    "problem_statement": "Users need a simple and efficient way to manage their personal tasks to stay organized.",
    "constraints": [
      "The application must be built using Java Spring Boot for the backend and Angular for the frontend."
    ]
  }

  onSectionSelect(section: string) {
    this.selectedSection = section;
  }

  isStackblitzActive() {
    return this.selectedFile === 'code-preview';
  }

  approveSpec() {
    this.loaderService.start();
    let message = "Here are the final edited specs: " + JSON.stringify(this.spec);
    this.wizardService.sendMessage("change").pipe(catchError(err => {
      console.log('Error caught:', err);
      return of(null); // fallback value
    })).subscribe((reply) => {
      this.wizardService.sendMessage(message).pipe(catchError(err => {
        console.log('Error caught:', err);
        return of(null); // fallback value
      })).subscribe((reply) => {
        console.log(reply);
        if ((reply as any).spec) {
          this.specService.setSpec((reply as any).spec);

          //approve specs
          this.wizardService.sendMessage("approve").pipe(catchError(err => {
            console.log('Error caught:', err);
            return of(null); // fallback value
          })).subscribe((reply) => {
            // Set artifacts if they exist in response
            if ((reply as any).nontech_artifacts_md) {
              this.specService.setNontechArtifacts((reply as any).nontech_artifacts_md);
            }
            if ((reply as any).technical_artifacts_md) {
              this.specService.setTechnicalArtifacts((reply as any).technical_artifacts_md);
            }

            // Stop loader
            this.loaderService.stop();

            // Switch to preview mode and populate files
            if (!this.isPreviewMode()) {
              this.isPreviewMode.set(true);
            }

            // Collect all filenames from both artifacts and update files
            const allFiles: string[] = [];
            const nontechArtifacts = this.specService.nontech_artifacts_md() as any;
            if (nontechArtifacts) {
              allFiles.push(...Object.keys(nontechArtifacts));
            }
            const technicalArtifacts = this.specService.technical_artifacts_md();
            if (technicalArtifacts) {
              allFiles.push(...Object.keys(technicalArtifacts));
            }
            
            this.files.set(allFiles.sort());
            this.selectedFile = allFiles.length > 0 ? allFiles[0] : 'requirements.md';

            console.log(reply);
          })
        }
      })
    })
  }

  generateCode() {
    this.loaderService.start();
    const projectId = 'project-' + Date.now();
    this.wizardService.sendMessage('generate-code').pipe(catchError(err => {
      console.log('Error caught:', err);
      this.loaderService.stop();
      return of(null);
    })).subscribe((reply) => {
      if ((reply as any).generated_code_files) {
        this.specService.setGeneratedCode((reply as any).generated_code_files.files);
        
        // Clear files and reset selectedFile to trigger code preview
        this.files.set([]);
        this.selectedFile = 'code-preview';
        
        this.loaderService.stop();
        console.log('Code generated successfully');
      } else {
        this.loaderService.stop();
        console.error('Code generation failed');
      }
    });
  }

  viewPrototype() {
    this.isPreviewMode.set(true);
    this.selectedFile = 'code-preview';
  }

  togglePreview() {
    this.isPreviewMode.update(previewMode => !previewMode);
    if (this.isPreviewMode()) {
      // Collect all filenames from both artifacts
      const allFiles: string[] = [];
      
      const nontechArtifacts = this.specService.nontech_artifacts_md();
      if (nontechArtifacts) {
        allFiles.push(...Object.keys(nontechArtifacts));
      }
      
      const technicalArtifacts = this.specService.technical_artifacts_md();
      if (technicalArtifacts) {
        allFiles.push(...Object.keys(technicalArtifacts));
      }
      
      this.files.set(allFiles.sort());
      this.selectedFile = allFiles.length > 0 ? allFiles[0] : 'requirements.md';
    } else {
      this.files.set([]);
      this.selectedFile = 'requirements.md';
    }
  }

  onFileSelect(file: string) {
    this.selectedFile = file;
  }

  getMdText(file: string): string {
    // Check if file exists in nontech artifacts
    const nontechArtifacts = this.specService.nontech_artifacts_md();
    if (nontechArtifacts && nontechArtifacts[file]) {
      return nontechArtifacts[file];
    }
    
    // Check if file exists in technical artifacts
    const technicalArtifacts = this.specService.technical_artifacts_md();
    if (technicalArtifacts && technicalArtifacts[file]) {
      return technicalArtifacts[file];
    }
    
    // Fallback: generate from spec for requirements.md
    if (file === 'requirements.md_test') {
      let md = `# Requirements Specification\n\n`;
      for (let key in this.spec) {
        md += `## ${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}\n\n`;
        const value = this.spec[key];
        if (Array.isArray(value)) {
          value.forEach((item: any) => {
            if (typeof item === 'object' && item !== null) {
              md += `- **${item.name || 'Item'}**: ${item.description || JSON.stringify(item)}\n`;
            } else {
              md += `- ${item}\n`;
            }
          });
        } else if (typeof value === 'object' && value !== null) {
          for (let subkey in value) {
            md += `- **${subkey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}**: ${value[subkey]}\n`;
          }
        } else {
          md += `${value}\n`;
        }
        md += '\n';
      }
      return md;
    }
    
    return `# ${file}\n\nContent not found for this file.`;
  }

}