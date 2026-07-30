/**
 * Copy text to the clipboard, reporting whether it worked.
 *
 * `navigator.clipboard` only exists in a *secure context* — HTTPS, or localhost.
 * A reqmesh deployment reached over plain HTTP on a LAN address therefore has no
 * Clipboard API at all, and the previous call site wrote
 * `navigator.clipboard?.writeText(...)` then unconditionally showed a tick: the
 * button reported success having copied nothing, on exactly the deployments most
 * likely to be used from a browser that had never been given a certificate.
 *
 * The fallback is the pre-Clipboard-API technique: a hidden textarea, a
 * selection, and `document.execCommand('copy')`. It is deprecated but still
 * implemented everywhere, and it works in an insecure context, which is the
 * whole point of having it here.
 *
 * Returns false rather than throwing, so callers can say so in the UI instead of
 * claiming a copy that never happened.
 */
export async function copyText(text: string): Promise<boolean> {
  // Preferred path. Can still reject — a document that is not focused, or a
  // permissions policy that forbids clipboard-write — so the fallback runs.
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* fall through */
    }
  }

  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    // Kept in the layout (execCommand ignores display:none) but out of sight and
    // out of the tab order, and readOnly so mobile keyboards stay down.
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);

    // Restore whatever the user had selected: silently clobbering a selection to
    // copy a link is its own small bug.
    const prev = document.getSelection()?.rangeCount
      ? document.getSelection()!.getRangeAt(0)
      : null;

    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    const ok = document.execCommand('copy');

    document.body.removeChild(ta);
    if (prev) {
      const sel = document.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(prev);
    }
    return ok;
  } catch {
    return false;
  }
}
