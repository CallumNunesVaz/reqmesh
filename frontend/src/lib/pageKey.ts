/**
 * The preference key for a route.
 *
 * Keyed on the route *section*, not the trailing path segment: on a detail
 * route like `/project/x/requirements/REQ-001` the last segment is the record
 * id, so keying on it gave every requirement its own remembered layout and grew
 * localStorage one key per visited record. All detail routes under a section
 * share the section's key.
 */
export function pageKeyFor(pathname: string): string {
  const segments = pathname.split('/').filter(Boolean);
  const section = segments[0] === 'project' && segments.length >= 3
    ? segments[2]
    : segments[0] === 'project'
      ? 'overview'
      : segments[segments.length - 1] || 'overview';
  return section.replace(/[^a-z0-9-]/gi, '');
}
