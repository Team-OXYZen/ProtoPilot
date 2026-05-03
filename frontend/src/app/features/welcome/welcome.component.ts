import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuthModalComponent } from '../../shared/components/auth-modal/auth-modal.component';

@Component({
  selector: 'app-welcome',
  standalone: true,
  imports: [CommonModule, AuthModalComponent],
  templateUrl: './welcome.component.html',
  styleUrl: './welcome.component.scss',
})
export class WelcomeComponent {
  showAuthModal = signal(false);
  isSignUp = signal(false);

  openLogin(): void {
    this.isSignUp.set(false);
    this.showAuthModal.set(true);
  }

  openSignUp(): void {
    this.isSignUp.set(true);
    this.showAuthModal.set(true);
  }

  closeModal(): void {
    this.showAuthModal.set(false);
  }
}
