import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { inject } from '@angular/core';
import { ThemeToggleComponent } from '../theme-toggle/theme-toggle.component';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, ThemeToggleComponent],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss',
})
export class HeaderComponent {
  @Input() showDashboardButton = true;
  @Input() rightContent: any; // Can contain custom action buttons

  private router = inject(Router);

  goToWelcome(): void {
    this.router.navigate(['/welcome']);
  }

  goToDashboard(): void {
    this.router.navigate(['/dashboard']);
  }
}
