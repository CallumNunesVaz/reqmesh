/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import type { ReactNode } from 'react';
import BlockNode from '../src/components/BlockNode';
import CircularNode from '../src/components/CircularNode';

vi.mock('@xyflow/react', () => ({
  Handle: () => null,
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
  useStore: (selector: (s: unknown) => unknown) =>
    selector({ transform: [0, 0, 0.75] }),
}));

vi.mock('../src/store/auth', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ canEdit: () => false }),
}));

// The node components take the full React Flow `NodeProps`, but these tests
// only drive them through `data`; alias to a minimal prop shape.
type AnyNodeProps = { id?: string; data: unknown };
const Block = BlockNode as unknown as (p: AnyNodeProps) => ReactNode;
const Circle = CircularNode as unknown as (p: AnyNodeProps) => ReactNode;

function findWithOpacity(container: HTMLElement, opacity: string): HTMLElement | null {
  for (const el of container.querySelectorAll<HTMLElement>('*')) {
    if (el.style.opacity === opacity) return el;
  }
  return null;
}

const blockData = {
  label: 'REQ-1',
  name: 'Reactor',
  status: 'proposed',
  priority: 'medium',
  type: 'functional',
  cascadeFrom: null,
  hasChildren: false,
  collapsed: false,
  childCount: 0,
  subgroupCount: 0,
  params: [],
  constraints: [],
  verdict: null,
  vcCount: 0,
  desc: '',
  hasMissingInfo: false,
};

const circleData = {
  label: 'REQ-1',
  name: 'Reactor',
  status: 'proposed',
  priority: 'medium',
  type: 'functional',
  cascadeFrom: null,
  childCount: 0,
  hasChildren: false,
  collapsed: false,
};

afterEach(cleanup);

describe('BlockNode selection styling', () => {
  it('dims when data.dimmed is true', () => {
    const { container } = render(<Block id="REQ-1" data={{ ...blockData, dimmed: true, isSelected: false } as any} />);
    expect(findWithOpacity(container, '0.18')).not.toBeNull();
  });

  it('is not dimmed when data.dimmed is false', () => {
    const { container } = render(<Block id="REQ-1" data={{ ...blockData, dimmed: false, isSelected: false } as any} />);
    expect(findWithOpacity(container, '0.18')).toBeNull();
  });

  it('draws the selection outline when data.isSelected is true', () => {
    const { container } = render(<Block id="REQ-1" data={{ ...blockData, dimmed: false, isSelected: true } as any} />);
    const outlined = Array.from(container.querySelectorAll<HTMLElement>('*'))
      .find((el) => el.style.boxShadow.includes('0 0 0 1px'));
    expect(outlined).not.toBeNull();
  });
});

describe('CircularNode selection styling', () => {
  it('dims when data.dimmed is true', () => {
    const { container } = render(<Circle id="REQ-1" data={{ ...circleData, dimmed: true, isSelected: false } as any} />);
    expect(findWithOpacity(container, '0.18')).not.toBeNull();
  });

  it('is not dimmed when data.dimmed is false', () => {
    const { container } = render(<Circle id="REQ-1" data={{ ...circleData, dimmed: false, isSelected: false } as any} />);
    expect(findWithOpacity(container, '0.18')).toBeNull();
  });

  it('draws the selection ring when data.isSelected is true', () => {
    const { container } = render(<Circle id="REQ-1" data={{ ...circleData, dimmed: false, isSelected: true } as any} />);
    expect(container.querySelector('circle[opacity="0.7"]')).not.toBeNull();
  });
});

describe('memo bails out when an unrelated node is selected', () => {
  function renderCounted(Component: (p: { data: unknown }) => ReactNode) {
    let reads = 0;
    const data: any = {
      ...blockData,
      get name() { reads += 1; return 'Reactor'; },
    };
    const { rerender } = render(<Component data={data} />);
    const afterFirst = reads;
    expect(afterFirst).toBeGreaterThan(0);
    // Same data reference = an unrelated selection left this node's data alone.
    rerender(<Component data={data} />);
    expect(reads).toBe(afterFirst);
  }

  it('BlockNode does not re-render for the same data object', () => {
    renderCounted(BlockNode as any);
  });

  it('CircularNode does not re-render for the same data object', () => {
    renderCounted(CircularNode as any);
  });
});
