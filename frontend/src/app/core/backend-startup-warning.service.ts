import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class BackendStartupWarningService {
  readonly isVisible = signal(false);

  private readonly slowRequests = new Set<symbol>();
  private readonly timers = new Map<symbol, ReturnType<typeof setTimeout>>();

  watchRequest(delayMs = 5000): symbol {
    const requestId = Symbol('backend-request');
    const timer = setTimeout(() => {
      this.timers.delete(requestId);
      this.slowRequests.add(requestId);
      this.isVisible.set(true);
    }, delayMs);

    this.timers.set(requestId, timer);
    return requestId;
  }

  finishRequest(requestId: symbol): void {
    const timer = this.timers.get(requestId);

    if (timer) {
      clearTimeout(timer);
      this.timers.delete(requestId);
    }

    this.slowRequests.delete(requestId);

    if (this.slowRequests.size === 0) {
      this.isVisible.set(false);
    }
  }
}
