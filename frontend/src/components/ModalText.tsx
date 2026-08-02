import { Fragment } from 'react';
import { modalRegex, modalStrength, type ModalStrength } from '../lib/qualityRules';

const MODAL_CLASSES: Record<ModalStrength, { cls: string; title: string }> = {
  binding: {
    cls: 'font-semibold uppercase tracking-wide text-cs-teal',
    title: 'Binding obligation',
  },
  advisory: {
    cls: 'font-semibold uppercase tracking-wide text-amber-400',
    title: 'Advisory — not a binding requirement',
  },
};

export function ModalText({ children }: { children: string }): JSX.Element {
  // The regex is g-flagged; a shared instance would carry lastIndex between
  // calls and make matches vanish on every other render.
  const re = modalRegex();
  const parts: { text: string; strength?: ModalStrength }[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(children)) !== null) {
    if (m.index > last) {
      parts.push({ text: children.slice(last, m.index) });
    }
    const word = m[0];
    const strength = modalStrength(word);
    if (strength) {
      parts.push({ text: word, strength });
    } else {
      parts.push({ text: word });
    }
    last = m.index + word.length;
  }
  if (last < children.length) {
    parts.push({ text: children.slice(last) });
  }

  if (parts.length === 0) return <>{children}</>;

  return (
    <>
      {parts.map((p, i) =>
        p.strength ? (
          <span key={i} className={MODAL_CLASSES[p.strength].cls} title={MODAL_CLASSES[p.strength].title}>
            {p.text}
          </span>
        ) : (
          <Fragment key={i}>{p.text}</Fragment>
        ),
      )}
    </>
  );
}
