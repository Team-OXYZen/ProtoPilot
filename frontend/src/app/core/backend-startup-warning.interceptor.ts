import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { finalize } from 'rxjs';

import { environment } from '../../environments/environment';
import { BackendStartupWarningService } from './backend-startup-warning.service';

export const backendStartupWarningInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(environment.apiBaseUrl)) {
    return next(req);
  }

  const warningService = inject(BackendStartupWarningService);
  const requestId = warningService.watchRequest();

  return next(req).pipe(
    finalize(() => warningService.finishRequest(requestId)),
  );
};
