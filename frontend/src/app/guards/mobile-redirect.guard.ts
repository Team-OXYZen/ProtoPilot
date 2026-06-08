import { inject, PLATFORM_ID } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { isPlatformBrowser } from '@angular/common';

const MOBILE_QUERY = '(max-width: 767px), (pointer: coarse) and (max-width: 1024px)';

export const mobileRedirectGuard: CanActivateFn = () => {
  const router = inject(Router);
  const platformId = inject(PLATFORM_ID);

  if (!isPlatformBrowser(platformId)) {
    return true;
  }

  return window.matchMedia(MOBILE_QUERY).matches ? router.createUrlTree(['/welcome']) : true;
};
