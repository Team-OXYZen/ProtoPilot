import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class SpecService {
  readonly spec = signal<any>({});
  readonly nontech_artifacts_md = signal<Record<string, string> | null>(null);
  readonly technical_artifacts_md = signal<Record<string, string> | null>(null);
  readonly angular_code_files = signal<Record<string, string> | null>(null);
  readonly java_code_files = signal<Record<string, string> | null>(null);
  readonly deployStatus = signal<'idle' | 'building' | 'running' | 'failed'>('idle');
  readonly deployUrl = signal<string | null>(null);
  readonly needsRedeploy = signal<boolean>(false);

  setSpec(spec: any): void {
    this.spec.set(spec);
  }

  updateSection(section: string, value: any): void {
    this.spec.update(current => ({ ...current, [section]: value }));
  }

  clearSpec(): void {
    this.spec.set({});
  }

  setNontechArtifacts(artifacts: Record<string, string>): void {
    this.nontech_artifacts_md.set(artifacts);
  }

  setTechnicalArtifacts(artifacts: Record<string, string>): void {
    this.technical_artifacts_md.set(artifacts);
  }

  setAngularCode(files: Record<string, string>): void {
    this.angular_code_files.set(files);
  }

  setJavaCode(files: Record<string, string>): void {
    this.java_code_files.set(files);
    this.needsRedeploy.set(false);
  }

  updateNontechArtifact(filename: string, content: string): void {
    this.nontech_artifacts_md.update(current => ({
      ...current,
      [filename]: content
    }));
  }

  updateTechnicalArtifact(filename: string, content: string): void {
    this.technical_artifacts_md.update(current => ({
      ...current,
      [filename]: content
    }));
  }

  clearArtifacts(): void {
    this.nontech_artifacts_md.set(null);
    this.technical_artifacts_md.set(null);
  }

  clearGeneratedCode(): void {
    this.angular_code_files.set(null);
    this.java_code_files.set(null);
  }

  setDeployStatus(status: 'idle' | 'building' | 'running' | 'failed', url?: string): void {
    this.deployStatus.set(status);
    this.deployUrl.set(url ?? null);
  }

  clearDeploy(): void {
    this.deployStatus.set('idle');
    this.deployUrl.set(null);
  }
}
