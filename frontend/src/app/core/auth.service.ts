import { Injectable, signal } from '@angular/core';
import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { User } from '../shared/models/user.model';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private platformId = inject(PLATFORM_ID);
  private isAuthenticatedSignal = signal<boolean>(false);
  private currentUserSignal = signal<User | null>(null);

  // Hardcoded credentials
  private readonly VALID_CREDENTIALS = {
    username: 'demo',
    password: 'demo123',
  };

  constructor() {
    this.initializeAuth();
  }

  private initializeAuth(): void {
    if (isPlatformBrowser(this.platformId)) {
      const savedUser = localStorage.getItem('currentUser');
      if (savedUser) {
        const user = JSON.parse(savedUser);
        this.currentUserSignal.set(user);
        this.isAuthenticatedSignal.set(true);
      }
    }
  }

  login(username: string, password: string): boolean {
    if (
      username === this.VALID_CREDENTIALS.username &&
      password === this.VALID_CREDENTIALS.password
    ) {
      const user: User = { username };
      this.currentUserSignal.set(user);
      this.isAuthenticatedSignal.set(true);
      
      if (isPlatformBrowser(this.platformId)) {
        localStorage.setItem('currentUser', JSON.stringify(user));
      }
      return true;
    }
    return false;
  }

  logout(): void {
    this.currentUserSignal.set(null);
    this.isAuthenticatedSignal.set(false);
    
    if (isPlatformBrowser(this.platformId)) {
      localStorage.removeItem('currentUser');
    }
  }

  isAuthenticated() {
    return this.isAuthenticatedSignal.asReadonly();
  }

  getCurrentUser() {
    return this.currentUserSignal.asReadonly();
  }
}
