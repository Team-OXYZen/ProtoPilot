import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { AuthModalComponent } from '../../shared/components/auth-modal/auth-modal.component';
import { ThemeToggleComponent } from '../../shared/components/theme-toggle/theme-toggle.component';

@Component({
  selector: 'app-welcome',
  standalone: true,
  imports: [CommonModule, AuthModalComponent, ThemeToggleComponent],
  templateUrl: './welcome.component.html',
  styleUrl: './welcome.component.scss',
})
export class WelcomeComponent {
  showAuthModal = signal(false);
  isSignUp = signal(false);

  private router = inject(Router);
  authService = inject(AuthService);

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

  goToDashboard(): void {
    this.router.navigate(['/dashboard']);
  }

  logout(): void {
    this.authService.logout();
  }
}
