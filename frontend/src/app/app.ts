import { Component, HostListener, inject, OnInit, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ThemeService } from './core/theme.service';
import { FooterComponent } from './shared/components/footer/footer.component';
import { LoaderComponent } from './shared/components/loader/loader.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, FooterComponent, LoaderComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit {
  private themeService = inject(ThemeService);
  readonly isUnsupportedViewport = signal(false);
  private readonly desktopMinWidth = 1024;

  ngOnInit(): void {
    // Theme is initialized in ThemeService constructor
    this.updateViewportSupport();
  }

  @HostListener('window:resize')
  onWindowResize(): void {
    this.updateViewportSupport();
  }

  private updateViewportSupport(): void {
    if (typeof window === 'undefined') {
      this.isUnsupportedViewport.set(false);
      return;
    }

    this.isUnsupportedViewport.set(window.innerWidth < this.desktopMinWidth);
  }
}
