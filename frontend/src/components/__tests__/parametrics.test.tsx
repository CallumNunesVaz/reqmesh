/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import { ExpressionField, MarginBar, ParametricsCard } from '../parametrics';
import type { ParamReference } from '../../lib/parametrics';
import type { Parameter } from '../../api/client';

// `ParametricsCard` reads the what-if state through `useWhatIf`. Mocking the
// module keeps the card's own render logic under test without dragging in the
// provider's auth store and network calls — and without adding a seam to
// `parametrics.tsx` that exists only for tests.
let whatIfOverrides: Record<string, number> = {};
let whatIfBase: Record<string, number | null> = {};
vi.mock('../WhatIfContext', () => ({
  useWhatIf: () => ({
    overrides: whatIfOverrides,
    base: whatIfBase,
    impact: null,
    pending: false,
    error: null,
    stepIndex: 0,
    playing: false,
    setOverride: () => {},
    removeOverride: () => {},
    evaluate: () => {},
    clear: () => {},
    apply: async () => {},
    setStepIndex: () => {},
    setPlaying: () => {},
  }),
}));

beforeEach(() => {
  whatIfOverrides = {};
  whatIfBase = { 'R-001.mtow': 1157 };
});

beforeAll(() => {
  // jsdom ships no `scrollIntoView`; the combobox's highlight-follow effect
  // calls it on the focused option and would throw on every ArrowDown.
  Element.prototype.scrollIntoView = () => {};
});

const REFS: ParamReference[] = [
  { ref: 'alpha', label: 'alpha' },
  { ref: 'beta', label: 'beta' },
  { ref: 'gamma', label: 'gamma' },
];

function ComboboxHarness() {
  const [value, setValue] = useState('');
  return <ExpressionField value={value} onChange={setValue} placeholder="expr" refs={REFS} />;
}

function textarea(container: HTMLElement): HTMLTextAreaElement {
  return container.querySelector('textarea') as HTMLTextAreaElement;
}

function openList(ta: HTMLTextAreaElement) {
  fireEvent.change(ta, { target: { value: 'a', selectionStart: 1, selectionEnd: 1 } });
}

describe('ExpressionField highlight mirror', () => {
  it.each([
    '',
    'GROS0001.mass - empty',
    'min(a, b) * 2.5e-3',
    "'unterminated",
    'GROS0',
  ])('mirror textContent round-trips %j exactly', (value) => {
    const { container } = render(<ExpressionField value={value} onChange={() => {}} refs={[]} />);
    const mirror = container.querySelector('[data-expr-highlight]');
    expect(mirror).not.toBeNull();
    expect(mirror!.textContent).toBe(value);
  });

  it('mirror carries aria-hidden so accessible-name queries skip it', () => {
    const { container } = render(<ExpressionField value="GROS0001.mass" onChange={() => {}} refs={[]} />);
    const mirror = container.querySelector('[data-expr-highlight]');
    expect(mirror).not.toBeNull();
    expect(mirror!.getAttribute('aria-hidden')).toBe('true');
  });

  it('an empty field with a placeholder is still findable by placeholder', () => {
    const { getByPlaceholderText } = render(
      <ExpressionField value="" onChange={() => {}} placeholder="or expr: GROS0001.mass - empty" refs={[]} />,
    );
    expect(getByPlaceholderText('or expr: GROS0001.mass - empty')).toBeTruthy();
  });

  it('token spans carry the colour class for their kind', () => {
    const { container } = render(
      <ExpressionField value="GROS0001.mass - 2.5e-3 + foo" onChange={() => {}} refs={[]} />,
    );
    const mirror = container.querySelector('[data-expr-highlight]') as HTMLElement;
    const classes = Array.from(mirror.querySelectorAll('span')).map((s) => s.className);
    expect(classes).toContain('text-cs-blue');
    expect(classes).toContain('text-cs-orange');
    expect(classes).toContain('text-cs-pink');
  });
});

describe('ExpressionField combobox ARIA', () => {
  it('closed: aria-expanded false with no activedescendant or controls attribute', () => {
    const { container } = render(<ComboboxHarness />);
    const ta = textarea(container);
    expect(ta.getAttribute('aria-expanded')).toBe('false');
    expect(ta.getAttribute('aria-activedescendant')).toBeNull();
    expect(ta.getAttribute('aria-controls')).toBeNull();
  });

  it('typing a matching fragment opens the list and points activedescendant at the first option', () => {
    const { container } = render(<ComboboxHarness />);
    const ta = textarea(container);
    openList(ta);
    const options = Array.from(container.querySelectorAll('[role="option"]'));
    expect(options.length).toBeGreaterThan(0);
    expect(ta.getAttribute('aria-expanded')).toBe('true');
    expect(ta.getAttribute('aria-activedescendant')).toBe(options[0].id);
  });

  it('ArrowDown moves activedescendant to the second option id', () => {
    const { container } = render(<ComboboxHarness />);
    const ta = textarea(container);
    openList(ta);
    const options = Array.from(container.querySelectorAll('[role="option"]'));
    fireEvent.keyDown(ta, { key: 'ArrowDown' });
    expect(ta.getAttribute('aria-activedescendant')).toBe(options[1].id);
  });

  it('ArrowUp at index 0 leaves activedescendant clamped on the first option', () => {
    const { container } = render(<ComboboxHarness />);
    const ta = textarea(container);
    openList(ta);
    const options = Array.from(container.querySelectorAll('[role="option"]'));
    fireEvent.keyDown(ta, { key: 'ArrowUp' });
    expect(ta.getAttribute('aria-activedescendant')).toBe(options[0].id);
  });

  it('every option has a unique non-empty id that activedescendant takes when highlighted', () => {
    const { container } = render(<ComboboxHarness />);
    const ta = textarea(container);
    openList(ta);
    const options = Array.from(container.querySelectorAll('[role="option"]'));
    const ids = options.map((o) => o.id);
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) expect(id.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
    for (let i = 0; i < options.length; i++) {
      expect(ta.getAttribute('aria-activedescendant')).toBe(options[i].id);
      if (i < options.length - 1) fireEvent.keyDown(ta, { key: 'ArrowDown' });
    }
  });

  it('Escape closes the list and removes activedescendant and controls', () => {
    const { container } = render(<ComboboxHarness />);
    const ta = textarea(container);
    openList(ta);
    fireEvent.keyDown(ta, { key: 'Escape' });
    expect(ta.getAttribute('aria-expanded')).toBe('false');
    expect(ta.getAttribute('aria-activedescendant')).toBeNull();
    expect(ta.getAttribute('aria-controls')).toBeNull();
  });
});

describe('MarginBar', () => {
  it('renders nothing when pct is undefined', () => {
    const { container } = render(<MarginBar margin={{ value: 5 }} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a green 15% bar for { value: 5, pct: 15 }', () => {
    const { container } = render(<MarginBar margin={{ value: 5, pct: 15 }} />);
    const bar = container.querySelector('[data-margin-bar]') as HTMLElement;
    expect(bar.getAttribute('data-margin-fill')).toBe('15');
    expect(bar.style.width).toBe('15%');
    expect(bar.className).toContain('bg-cs-green/10');
  });

  it('clamps a negative over-100% margin to 100 and turns red', () => {
    const { container } = render(<MarginBar margin={{ value: -3, pct: -250 }} />);
    const bar = container.querySelector('[data-margin-bar]') as HTMLElement;
    expect(bar.getAttribute('data-margin-fill')).toBe('100');
    expect(bar.style.width).toBe('100%');
    expect(bar.className).toContain('bg-cs-red/10');
  });

  it('zero margin is green with zero fill', () => {
    const { container } = render(<MarginBar margin={{ value: 0, pct: 0 }} />);
    const bar = container.querySelector('[data-margin-bar]') as HTMLElement;
    expect(bar.getAttribute('data-margin-fill')).toBe('0');
    expect(bar.className).toContain('bg-cs-green/10');
  });

  it('is aria-hidden and absolutely positioned (decorative)', () => {
    const { container } = render(<MarginBar margin={{ value: 5, pct: 15 }} />);
    const bar = container.querySelector('[data-margin-bar]') as HTMLElement;
    expect(bar.getAttribute('aria-hidden')).toBe('true');
    expect(bar.className).toContain('absolute');
  });
});

/**
 * The what-if override input masks a parameter's value while a replacement is
 * typed. The struck-through baseline beside it must appear exactly once: the
 * `isOverridden` branch already renders `original -> override`, so rendering the
 * baseline unconditionally next to the input showed the same number twice as
 * soon as the user typed anything.
 */
describe('what-if override baseline', () => {
  const BASE_REF = 'R-001.mtow';

  function renderCard(overrides: Record<string, number>) {
    whatIfOverrides = overrides;
    return render(
      <ParametricsCard
        reqId="R-001"
        parameters={[{ name: 'mtow', value: 1157, unit: 'kg' } as Parameter]}
        constraints={[]}
        // `ParametricsCard` only wires up what-if in edit mode
        // (`const whatIf = editable ? whatIfCtx : null`).
        editable
        onSave={() => {}}
      />,
    );
  }

  function openOverrideInput(container: HTMLElement) {
    fireEvent.click(container.querySelector('button[title="What-if override"]')!);
  }

  it('renders the baseline once while the override is still uncommitted', () => {
    const { container } = renderCard({});
    openOverrideInput(container);
    expect(container.querySelector('input[type="number"]')).not.toBeNull();
    const shown = container.querySelectorAll('[data-override-baseline]');
    expect(shown.length).toBe(1);
    expect(shown[0].textContent).toBe('1157');
  });

  it('still renders the baseline once after the override is committed', () => {
    const { container } = renderCard({ [BASE_REF]: 1200 });
    openOverrideInput(container);
    expect(container.querySelector('input[type="number"]')).not.toBeNull();
    const shown = container.querySelectorAll('[data-override-baseline]');
    expect(shown.length).toBe(1);
    expect(shown[0].textContent).toBe('1157');
  });

  it('renders no baseline at all until the override input is opened', () => {
    const { container } = renderCard({});
    expect(container.querySelectorAll('[data-override-baseline]').length).toBe(0);
  });

  it('prefers the what-if base over the parameter value as the baseline', () => {
    // `base` is what the input is actually masking. Were the span sourced from
    // `p.value` the two would coincide here only by accident.
    whatIfBase = { [BASE_REF]: 900 };
    const { container } = renderCard({});
    openOverrideInput(container);
    expect(container.querySelector('[data-override-baseline]')!.textContent).toBe('900');
  });
});
