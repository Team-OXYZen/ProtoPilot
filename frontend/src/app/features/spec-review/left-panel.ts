import { Component, inject, Input, Output, EventEmitter } from '@angular/core';
import { SpecService } from './services/spec.service';

@Component({
  selector: 'app-left-panel',
  standalone: true,
  templateUrl: './left-panel.html',
  styleUrl: './left-panel.scss'
})
export class LeftPanelComponent {

  private specService = inject(SpecService);
  @Input() selectedSection: string = '';
  @Input() files: string[] = [];
  @Input() selectedFile: string = '';
  @Output() sectionSelected = new EventEmitter<string>();
  @Output() fileSelected = new EventEmitter<string>();

  collapsedGroups: Record<string, boolean> = {
    product: false,
    technical: false,
    other: false,
  };

  private productDocOrder = [
    'Product_Brief.md',
    'User_Needs_and_Actions.md',
    'User_Stories_for_Jira.md',
    'User_Journey_and_Screens.md',
    'Screen_and_Interaction_Plan.md',
    'Prototype_Acceptance_Checklist.md',
  ];

  private technicalDocOrder = [
    'Technical_Architecture_Diagram.mmd',
    'Technical_Architecture_Notes.md',
    'Data_Model_Diagram.mmd',
    'Data_Dictionary.md',
    'Backend_API_Reference.md',
    'Codebase_Organization.md',
  ];

  get spec() {
    return this.specService.spec();
  }

  get sections(): string[] {
    return Object.keys(this.spec).sort();
  }

  get productFiles(): string[] {
    return this.orderedFiles(this.productDocOrder);
  }

  get technicalFiles(): string[] {
    return this.orderedFiles(this.technicalDocOrder);
  }

  get otherFiles(): string[] {
    const known = new Set([...this.productDocOrder, ...this.technicalDocOrder, 'code-preview']);
    return this.files.filter(file => !known.has(file)).sort();
  }

  selectSection(section: string) {
    this.sectionSelected.emit(section);
  }

  selectFile(file: string) {
    this.fileSelected.emit(file);
  }

  toggleGroup(group: 'product' | 'technical' | 'other') {
    this.collapsedGroups[group] = !this.collapsedGroups[group];
  }

  toTitleCase(str: string): string {
    return str?.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  }

  displayFileName(file: string): string {
    return file.replace(/\.(md|mmd)$/i, '').split('_').join(' ');
  }

  private orderedFiles(order: string[]): string[] {
    const available = new Set(this.files);
    return order.filter(file => available.has(file));
  }

}
