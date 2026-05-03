import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
import { WelcomeComponent } from './features/welcome/welcome.component';
import { DashboardComponent } from './features/dashboard/dashboard.component';
import { WizardComponent } from './features/requirements/components/wizard/wizard';
import { ReviewWrapperComponent } from './features/spec-review/review-wrapper';

export const routes: Routes = [
  {
    path: 'welcome',
    component: WelcomeComponent,
  },
  {
    path: 'dashboard',
    component: DashboardComponent,
    canActivate: [authGuard],
  },
  {
    path: 'requirements',
    component: WizardComponent,
    canActivate: [authGuard],
  },
  {
    path: 'spec-review',
    component: ReviewWrapperComponent,
    canActivate: [authGuard],
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
