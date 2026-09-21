/**
 * Resolve the selected bank from both locale-prefixed public routes and the
 * compatibility route used by older bookmarks.
 */
export function bankIdFromPathname(pathname: string | null | undefined): string | null {
  const match = pathname?.match(/(?:^|\/)banks\/([^/?]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}
