/**
 * Guards the post-login `?next=` redirect against off-origin and `javascript:`
 * sinks.
 *
 * After a successful login the SPA writes `window.location.href = next` with a
 * value read straight off the query string. Nothing constrains it to this
 * origin, so a crafted link redirects a freshly-authenticated user anywhere —
 * credible phishing, because the user really did just authenticate on the real
 * site — and a `javascript:` URL assigned to `location.href` is a known XSS
 * sink. Only a same-origin path is allowed through; everything else returns
 * `null` and the caller leaves the user where they are.
 */

/** Tab, line feed and carriage return. The URL parser removes these from
 *  *anywhere* in a URL, not just the front, so they must all go before the
 *  value is tested — otherwise `/\n/evil.example` reads as a same-origin path
 *  here but resolves to `//evil.example` in the browser. */
const URL_STRIPPED_CHARS = /[\t\n\r]/g;

/** Leading ASCII whitespace and remaining C0 controls (space, and everything
 *  below 0x20 except tab/LF/CR, which are already gone) that browsers ignore
 *  when parsing a URL. Strip these after the tab/LF/CR pass, or a `javascript:`
 *  URL preceded by a space slips through as "a path". */
const LEADING_STRIP_RE = /^[\0-\x20]+/;

/** The path to navigate to after login, or null if the value is not a safe
 *  same-origin path. Returns the sanitised value, never the input: the string
 *  handed to `location.href` must be exactly the string that was validated. */
export function safeNext(next: string | null | undefined): string | null {
  if (typeof next !== 'string') return null;

  // Order matters: remove tab/LF/CR everywhere, then strip leading whitespace
  // and the remaining C0 controls, then test what is left.
  const cleaned = next.replace(URL_STRIPPED_CHARS, '');
  const stripped = cleaned.replace(LEADING_STRIP_RE, '');

  if (stripped.length === 0) return null;
  if (!stripped.startsWith('/')) return null;
  // Protocol-relative — inherits the page scheme and leaves the deployment.
  if (stripped.startsWith('//')) return null;
  // A backslash is a forward slash to the parser, so `/` followed by `\` is
  // also protocol-relative (and Chrome treats a backslash-prefixed host as
  // off-origin).
  if (stripped.startsWith('/\\')) return null;
  // Browsers normalise backslashes to forward slashes anywhere, so a
  // backslash in the middle can turn a same-origin-looking path into a host.
  if (stripped.includes('\\')) return null;

  return stripped;
}
