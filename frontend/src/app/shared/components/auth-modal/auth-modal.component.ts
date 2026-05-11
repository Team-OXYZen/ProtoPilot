import { Component, inject, signal, output, input, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/auth.service';

@Component({
  selector: 'app-auth-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './auth-modal.component.html',
  styleUrl: './auth-modal.component.scss',
})
export class AuthModalComponent {

  private _isSignUp = signal(false);

  @Input() set isSignUp(value: boolean) {
    this._isSignUp.set(value);
  }

  get isSignUp() {
    return this._isSignUp();
  }

  username = signal('');
  password = signal('');
  passwordConfirm = signal('');
  errorMessage = signal('');
  isLoading = signal(false);
  
  closeModal = output<void>();

  private authService = inject(AuthService);
  private router = inject(Router);

  toggleMode(): void {
    this._isSignUp.set(!this._isSignUp());
    this.clearForm();
  }

  close(): void {
    this.closeModal.emit();
  }

  clearForm(): void {
    this.username.set('');
    this.password.set('');
    this.passwordConfirm.set('');
    this.errorMessage.set('');
  }

  onSubmit(): void {
    this.errorMessage.set('');

    if (!this.username() || !this.password()) {
      this.errorMessage.set('Please fill in all fields');
      return;
    }

    if (this._isSignUp() && this.password() !== this.passwordConfirm()) {
      this.errorMessage.set('Passwords do not match');
      return;
    }

    this.isLoading.set(true);

    // Simulate API call delay
    setTimeout(() => {
      const success = this.authService.login(this.username(), this.password());

      if (success) {
        this.isLoading.set(false);
        this.router.navigate(['/dashboard']);
      } else {
        this.errorMessage.set('Invalid credentials. Try demo / demo123');
        this.isLoading.set(false);
      }
    }, 300);
  }
}
