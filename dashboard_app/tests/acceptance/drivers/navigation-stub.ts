/**
 * Stand-in for the parts of `next/navigation` that need a mounted App Router.
 * Tests read `navigation.refresh` to see whether a page re-rendered itself
 * and set `navigation.pathname` to the route being viewed.
 */

import { vi } from "vitest";

export const navigation = {
  pathname: "/" as string,
  refresh: vi.fn(),
  reset(): void {
    this.pathname = "/";
    this.refresh.mockClear();
  }
};

const noop = () => undefined;

export const navigationOverrides = {
  usePathname: () => navigation.pathname,
  useRouter: () => ({
    back: noop,
    forward: noop,
    prefetch: noop,
    push: noop,
    refresh: navigation.refresh,
    replace: noop
  }),
  useSearchParams: () => new URLSearchParams()
};
