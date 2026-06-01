import { Injectable, signal } from '@angular/core';
import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { catchError, map, Observable, of, tap } from 'rxjs';
import { User } from '../shared/models/user.model';
import { environment } from '../../environments/environment';

interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private platformId = inject(PLATFORM_ID);
  private http = inject(HttpClient);
  private isAuthenticatedSignal = signal<boolean>(false);
  private currentUserSignal = signal<User | null>(null);
  private readonly apiUrl = `${environment.apiBaseUrl}/auth`;
  private readonly tokenKey = 'accessToken';
  private readonly userKey = 'currentUser';

  constructor() {
    this.initializeAuth();
  }

  private initializeAuth(): void {
    if (isPlatformBrowser(this.platformId)) {
      const token = localStorage.getItem(this.tokenKey);
      const savedUser = localStorage.getItem(this.userKey);
      if (token && savedUser) {
        const user = JSON.parse(savedUser);
        this.currentUserSignal.set(user);
        this.isAuthenticatedSignal.set(true);
      }
    }
  }

  login(username: string, password: string): Observable<boolean> {
    return this.http
      .post<AuthResponse>(`${this.apiUrl}/login`, { username, password })
      .pipe(
        tap((response) => this.setSession(response)),
        map(() => true),
        catchError(() => of(false)),
      );
  }

  signup(username: string, password: string): Observable<boolean> {
    return this.http
      .post<AuthResponse>(`${this.apiUrl}/signup`, { username, password })
      .pipe(
        tap((response) => this.setSession(response)),
        map(() => true),
        catchError(() => of(false)),
      );
  }

  getToken(): string | null {
    if (!isPlatformBrowser(this.platformId)) {
      return null;
    }

    return localStorage.getItem(this.tokenKey);
  }

  logout(): void {
    this.currentUserSignal.set(null);
    this.isAuthenticatedSignal.set(false);
    
    if (isPlatformBrowser(this.platformId)) {
      localStorage.removeItem(this.tokenKey);
      localStorage.removeItem(this.userKey);
    }
  }

  isAuthenticated() {
    return this.isAuthenticatedSignal.asReadonly();
  }

  getCurrentUser() {
    return this.currentUserSignal.asReadonly();
  }

  private setSession(response: AuthResponse): void {
    this.currentUserSignal.set(response.user);
    this.isAuthenticatedSignal.set(true);

    if (isPlatformBrowser(this.platformId)) {
      localStorage.setItem(this.tokenKey, response.access_token);
      localStorage.setItem(this.userKey, JSON.stringify(response.user));
    }
  }
}
