/**
 * Client-side mirror of `backend/app/services/sanitize.is_safe_external_url`.
 *
 * The backend blanks unsafe URLs when a project is read off disk, so this is
 * belt-and-braces rather than the only guard — but it is the check standing
 * between a stored `javascript:` value and an `href` on the viewer's page, and
 * it costs nothing. Keep the two in step; `tests/safeUrl.test.ts` pins the same
 * cases the Python test does.
 */

/** Schemes a stored link may carry. Allowlist, never a denylist of `javascript:`
 *  — a denylist loses to case tricks and embedded control characters. */
export const SAFE_URL_SCHEMES = ['http', 'https', 'mailto'];

const SCHEME_RE = /^\s*([A-Za-z][A-Za-z0-9+.-]*)\s*:/;

/** True if `url` is safe to place in an href. */
export function isSafeExternalUrl(url: string | null | undefined): boolean {
  if (!url || !url.trim()) return false;
  // Browsers ignore NUL/tab/newline/CR when resolving a URL — `java\tscript:`
  // navigates — so they must go before the scheme is read, or this check
  // disagrees with the parser that actually matters.
  const cleaned = url.replace(/[\0\t\n\r]/g, '');
  const m = SCHEME_RE.exec(cleaned);
  if (m === null) {
    // Relative reference. Reject protocol-relative `//host`, which inherits the
    // page scheme and leaves the deployment.
    return !cleaned.trim().startsWith('//');
  }
  return SAFE_URL_SCHEMES.includes(m[1].toLowerCase());
}
