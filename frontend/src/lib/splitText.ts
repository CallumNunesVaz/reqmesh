export interface SplitCandidate {
  text: string;
  name: string;
}

const MIN_LENGTH = 15;
const MAX_NAME = 60;

export function splitDescription(html: string): SplitCandidate[] {
  const tagless = html.replace(/<[^>]+>/g, ' ');
  if (!tagless.trim()) return [];

  const clauses = tagless.split(/(?<=[.;])\s+|(?<=\n)\s*/);
  const candidates = clauses
    .map((c) => c.replace(/\s+/g, ' ').trim())
    .filter((c) => c.length >= MIN_LENGTH);

  if (candidates.length < 2) return [];

  return candidates.map((text) => {
    let name = text;
    if (name.length > MAX_NAME) {
      const slice = name.slice(0, MAX_NAME);
      const lastSpace = slice.lastIndexOf(' ');
      name = lastSpace > 0 ? slice.slice(0, lastSpace) : slice;
    }
    return { text, name };
  });
}
