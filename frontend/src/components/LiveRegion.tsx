import { createContext, useCallback, useContext, useRef, useState } from 'react';

export type Politeness = 'polite' | 'assertive';

type Announce = (message: string, politeness?: Politeness) => void;

const AnnounceCtx = createContext<Announce>(() => {});

/** Returns a stable `announce` callback. */
export function useAnnounce(): Announce {
  return useContext(AnnounceCtx);
}

/**
 * A shared, always-mounted pair of live-region nodes. Every `useAnnounce`
 * consumer writes into one of the two, so anything that resolves without a
 * toast can still reach a screen reader.
 *
 * The nodes must exist from first render and never unmount: a live region
 * inserted at the same moment as its text is not reliably announced.
 */
export function LiveRegionProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [politeText, setPoliteText] = useState('');
  const [assertiveText, setAssertiveText] = useState('');
  const lastPolite = useRef('');
  const lastAssertive = useRef('');
  const repeat = useRef(false);

  const announce = useCallback<Announce>((message, politeness = 'polite') => {
    if (!message) return;
    const last = politeness === 'assertive' ? lastAssertive : lastPolite;
    let text = message;
    if (last.current === message) {
      // A screen reader ignores an unchanged text node, so disambiguate a
      // back-to-back repeat with a trailing zero-width space.
      repeat.current = !repeat.current;
      text = message + (repeat.current ? '\u200b' : '\u200b\u200b');
    }
    last.current = message;
    if (politeness === 'assertive') setAssertiveText(text);
    else setPoliteText(text);
  }, []);

  return (
    <AnnounceCtx.Provider value={announce}>
      {children}
      <output
        aria-live="polite"
        aria-atomic="true"
        data-live-region="polite"
        className="sr-only"
      >
        {politeText}
      </output>
      {/* No `role="alert"` here, deliberately. It would be redundant with
          `aria-live="assertive"`, and this node is always mounted — so it would
          make `[role=alert]` match permanently, which the app reserves for
          toasts. truncation-banner.spec.ts asserts `[role=alert]` has count 0,
          and three write-failures/relation specs match a single alert; all four
          broke on the version that carried the role. */}
      <div
        aria-live="assertive"
        aria-atomic="true"
        data-live-region="assertive"
        className="sr-only"
      >
        {assertiveText}
      </div>
    </AnnounceCtx.Provider>
  );
}
