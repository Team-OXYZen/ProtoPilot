import { Injectable, signal, effect } from '@angular/core';

export type Theme = 'dark' | 'light';

@Injectable({
  providedIn: 'root'
})
export class ThemeService {
  private readonly THEME_STORAGE_KEY = 'protopilot-theme';
  private readonly DEFAULT_THEME: Theme = 'dark';
  private readonly isServer = typeof window === 'undefined';

  // Signal to track current theme
  currentTheme = signal<Theme>(this.DEFAULT_THEME);

  constructor() {
    // Only initialize theme on client-side
    if (!this.isServer) {
      this.initializeTheme();

      // Effect to update DOM whenever theme changes
      effect(() => {
        this.applyTheme(this.currentTheme());
      });
    }
  }

  /**
   * Initialize theme from localStorage or system preference
   */
  private initializeTheme(): void {
    // Check localStorage first
    const savedTheme = this.getStoredTheme();
    if (savedTheme) {
      this.currentTheme.set(savedTheme);
      this.applyTheme(savedTheme); // Apply immediately to prevent flash
      return;
    }

    // Fall back to system preference
    const systemTheme = this.getSystemTheme();
    this.currentTheme.set(systemTheme);
    this.applyTheme(systemTheme); // Apply immediately to prevent flash
  }

  /**
   * Get theme from localStorage
   */
  private getStoredTheme(): Theme | null {
    if (this.isServer) return null;

    try {
      const stored = localStorage.getItem(this.THEME_STORAGE_KEY);
      if (stored === 'dark' || stored === 'light') {
        return stored;
      }
    } catch (e) {
      console.warn('Could not access localStorage:', e);
    }
    return null;
  }

  /**
   * Detect system theme preference
   */
  private getSystemTheme(): Theme {
    if (this.isServer || typeof window === 'undefined') {
      return this.DEFAULT_THEME;
    }

    if (window.matchMedia) {
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      return isDark ? 'dark' : 'light';
    }
    return this.DEFAULT_THEME;
  }

  /**
   * Apply theme to DOM and localStorage
   */
  private applyTheme(theme: Theme): void {
    if (this.isServer) return;

    // Set data-theme attribute on html element
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme);
    }

    // Save to localStorage
    try {
      localStorage.setItem(this.THEME_STORAGE_KEY, theme);
    } catch (e) {
      console.warn('Could not save theme to localStorage:', e);
    }
  }

  /**
   * Toggle between dark and light theme
   */
  toggleTheme(): void {
    const newTheme = this.currentTheme() === 'dark' ? 'light' : 'dark';
    this.currentTheme.set(newTheme);
  }

  /**
   * Set specific theme
   */
  setTheme(theme: Theme): void {
    this.currentTheme.set(theme);
  }

  /**
   * Get current theme
   */
  getTheme(): Theme {
    return this.currentTheme();
  }

  /**
   * Check if dark mode is active
   */
  isDarkMode(): boolean {
    return this.currentTheme() === 'dark';
  }

  /**
   * Listen to theme changes (for backwards compatibility or special use cases)
   */
  getThemeObservable() {
    // Convert signal to observable if needed (optional, for RxJS compatibility)
    // This is a simple implementation; you can enhance with toObservable() if using Angular 16+
    return this.currentTheme;
  }
}
