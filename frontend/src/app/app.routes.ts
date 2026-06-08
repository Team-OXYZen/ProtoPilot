import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
import { mobileRedirectGuard } from './guards/mobile-redirect.guard';

export const routes: Routes = [
  {
    path: 'welcome',
    loadComponent: () =>
      import('./features/welcome/welcome.component').then(m => m.WelcomeComponent),
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
    canActivate: [mobileRedirectGuard, authGuard],
  },
  {
    path: 'requirements',
    loadComponent: () =>
      import('./features/requirements/components/wizard/wizard').then(m => m.WizardComponent),
    canActivate: [mobileRedirectGuard, authGuard],
  },
  {
    path: 'spec-review',
    loadComponent: () =>
      import('./features/spec-review/review-wrapper').then(m => m.ReviewWrapperComponent),
    canActivate: [mobileRedirectGuard, authGuard],
  },
  {
    path: '',
    redirectTo: '/welcome',
    pathMatch: 'full',
  },
  {
    path: '**',
    redirectTo: '/welcome',
  },
];
