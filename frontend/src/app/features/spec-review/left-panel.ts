import { Component, inject, Input, Output, EventEmitter } from '@angular/core';
import { SpecService } from './services/spec.service';

@Component({
  selector: 'app-left-panel',
  standalone: true,
  templateUrl: './left-panel.html',
  styleUrl: './left-panel.css'
})
export class LeftPanelComponent {

  private specService = inject(SpecService);
  @Input() selectedSection: string = '';
  @Input() files: string[] = [];
  @Input() selectedFile: string = '';
  @Output() sectionSelected = new EventEmitter<string>();
  @Output() fileSelected = new EventEmitter<string>();

  get spec() {
    return this.specService.spec();
  }

  get sections(): string[] {
    return Object.keys(this.spec).sort();
  }

  selectSection(section: string) {
    this.sectionSelected.emit(section);
  }

  selectFile(file: string) {
    this.fileSelected.emit(file);
  }

  toTitleCase(str: string): string {
    return str.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  }

}