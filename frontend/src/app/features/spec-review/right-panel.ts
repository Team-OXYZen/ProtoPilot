import { JsonPipe, CommonModule } from '@angular/common';
import { Component, inject, Input, OnChanges, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MarkdownModule } from 'ngx-markdown';
import { WizardService } from '../requirements/services/wizard-service';
import { SpecService } from './services/spec.service';
import { catchError, of } from 'rxjs';
import mermaid from 'mermaid';
import { LivePreviewComponent } from './components/live-preview/live-preview.component';

@Component({
  selector: 'app-right-panel',
  standalone: true,
  imports: [FormsModule, JsonPipe, MarkdownModule, CommonModule, LivePreviewComponent],
  templateUrl: './right-panel.html',
  styleUrl: './right-panel.scss'
})
export class RightPanelComponent implements OnChanges, AfterViewInit {

  @Input() selectedSection: string = '';
  @Input() mdText: string = '';
  @Input() isPreviewMode: boolean = false;
  @Input() selectedFile: string = '';
  @ViewChild('mermaidContainer', { static: false }) mermaidContainer?: ElementRef;

  isEditing: boolean = false;
  editedValue: string = '';
  editedArray: string[] = [];
  editedObjects: any[] = [];
  chatMessage: string = '';
  wizardService = inject(WizardService);
  specService = inject(SpecService);

  constructor() {
    mermaid.initialize({ startOnLoad: false });
  }

  ngAfterViewInit() {
    if (this.isMermaidDiagram(this.mdText)) {
      this.renderMermaid();
    }
  }

  ngOnChanges() {
    this.isEditing = false;
    // Re-render mermaid if content changed
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
        mermaidCode = mermaidCode.replace(/\(/g, '&lpar;').replace(/\)/g, '&rpar;');        
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
    return this.specService.generated_code_files();
  }

  createStackBlitzProject(): any {
    const generatedCode = this.specService.generated_code_files();
    if (!generatedCode) return null;

    return {
      files: generatedCode,
      title: 'Generated Angular Project',
      description: 'Auto-generated Angular project from ProtoPilot',
    };
  }

  openStackBlitz(): void {
    const generatedCode = this.specService.generated_code_files();
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

  startEdit() {
    this.isEditing = true;
    const data = this.selectedData;
    const isString = typeof data === 'string';
    const isStringArray = this.isStringArray;
    const isObjectArray = this.isObjectArray;
    const isObject = this.isObject;

    if (isString) {
      this.editedValue = data;
    } else if (isStringArray) {
      this.editedArray = [...data];
    } else if (isObjectArray) {
      this.editedObjects = JSON.parse(JSON.stringify(data));
    } else if (isObject) {
      this.editedObjects = [JSON.parse(JSON.stringify(data))];
    } else {
      this.editedValue = JSON.stringify(data, null, 2);
    }
  }

  saveEdit() {
    try {
      const data = this.selectedData;
      const isString = typeof data === 'string';
      const isStringArray = this.isStringArray;
      const isObjectArray = this.isObjectArray;
      const isObject = this.isObject;

        if (isString) {
        this.specService.updateSection(this.selectedSection, this.editedValue);
      } else if (isStringArray) {
        this.specService.updateSection(this.selectedSection, this.editedArray);
      } else if (isObjectArray) {
        this.specService.updateSection(this.selectedSection, this.editedObjects);
      } else if (isObject) {
        this.specService.updateSection(this.selectedSection, this.editedObjects[0]);
      } else {
        this.specService.updateSection(this.selectedSection, JSON.parse(this.editedValue));
      }
      this.isEditing = false;
    } catch (e) {
      alert('Invalid input');
    }
  }

  cancelEdit() {
    this.isEditing = false;
  }

  addItem() {
    this.editedArray.push('');
  }

  removeItem(index: number) {
    this.editedArray.splice(index, 1);
  }

  addObject() {
    const template = this.editedObjects.length > 0 ? {...this.editedObjects[0]} : {};
    Object.keys(template).forEach(k => template[k] = '');
    this.editedObjects.push(template);
  }

  removeObject(index: number) {
    this.editedObjects.splice(index, 1);
  }

  sendChatMessage() {
    if (this.chatMessage) {
      this.wizardService.sendMessage(this.chatMessage).pipe(catchError(err => {
                console.log('Error caught:', err);
                return of(null); // fallback value
              })).subscribe(response => {
        if (response) {
          // Update spec based on response
          console.log('Response received: ' + JSON.stringify(response));
        }
        this.chatMessage = '';
      });
    }
  }

}