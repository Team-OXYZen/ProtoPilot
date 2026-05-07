import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface LoaderState {
  isLoading: boolean;
  message: string;
}

@Injectable({
  providedIn: 'root'
})
export class LoaderService {
  private loaderStateSubject = new BehaviorSubject<LoaderState>({
    isLoading: false,
    message: ''
  });

  public loaderState$: Observable<LoaderState> = this.loaderStateSubject.asObservable();

  private messageSequence = ['Thinking...', 'Almost there...', 'Processing...', 'Loading...'];
  private messageIndex = 0;
  private messageInterval: any;

  constructor() {}

  /**
   * Start the loader with cycling messages
   */
  start(): void {
    if (this.messageInterval) {
      clearInterval(this.messageInterval);
    }
    this.messageIndex = 0;
    this.loaderStateSubject.next({
      isLoading: true,
      message: this.messageSequence[this.messageIndex]
    });

    // Change message every 1.5 seconds
    this.messageInterval = setInterval(() => {
      this.messageIndex = (this.messageIndex + 1) % this.messageSequence.length;
      this.loaderStateSubject.next({
        isLoading: true,
        message: this.messageSequence[this.messageIndex]
      });
    }, 1500);
  }

  /**
   * Start the loader with a custom message sequence
   */
  startWithMessages(messages: string[]): void {
    if (messages.length === 0) {
      this.start();
      return;
    }

    if (this.messageInterval) {
      clearInterval(this.messageInterval);
    }
    this.messageSequence = messages;
    this.messageIndex = 0;
    this.loaderStateSubject.next({
      isLoading: true,
      message: this.messageSequence[this.messageIndex]
    });

    this.messageInterval = setInterval(() => {
      this.messageIndex = (this.messageIndex + 1) % this.messageSequence.length;
      this.loaderStateSubject.next({
        isLoading: true,
        message: this.messageSequence[this.messageIndex]
      });
    }, 1500);
  }

  /**
   * Stop the loader
   */
  stop(): void {
    if (this.messageInterval) {
      clearInterval(this.messageInterval);
    }
    this.loaderStateSubject.next({
      isLoading: false,
      message: ''
    });
  }

  /**
   * Get current loader state
   */
  getState(): LoaderState {
    return this.loaderStateSubject.value;
  }

  /**
   * Show loader with a static message
   */
  showWithMessage(message: string): void {
    if (this.messageInterval) {
      clearInterval(this.messageInterval);
    }
    this.loaderStateSubject.next({
      isLoading: true,
      message: message
    });
  }
}
