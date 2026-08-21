/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import RisksPage from '../RisksPage';
import { api } from '../../api/client';
import type { Risk, RiskMatrix } from '../../api/client';

vi.mock('../../api/client', () => ({
  api: {
    listRisks: vi.fn(),
    getRiskMatrix: vi.fn(),
    getRequirementTree: vi.fn(),
    getComponentTree: vi.fn(),
    getNextId: vi.fn(),
    createRisk: vi.fn(),
    updateRisk: vi.fn(),
    bulkUpdateRisks: vi.fn(),
    bulkDeleteRisks: vi.fn(),
  },
  RISK_STATUSES: ['open', 'mitigating', 'monitoring', 'accepted', 'closed'],
}));

vi.mock('../../store/auth', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ canPropose: () => false, canEdit: () => false }),
}));

vi.mock('../../store', () => ({
  useStore: (selector: (s: unknown) => unknown) => selector({ dataVersion: 0 }),
}));

vi.mock('../../components/entities', () => ({
  CopyLinkButton: () => null,
}));

vi.mock('../../components/useFocusedEntity', () => ({
  useFocusedEntity: () => null,
}));

vi.mock('../../components/RichTextEditor', () => ({
  default: () => null,
}));

vi.mock('../../components/Toast', () => ({
  useToasts: () => ({ addToast: vi.fn() }),
}));

vi.mock('../../hooks/useRangeSelection', () => ({
  useRangeSelection: () => ({ selectedIds: new Set(), select: vi.fn(), setSelectedIds: vi.fn() }),
}));

vi.mock('../../hooks/useBulkActions', () => ({
  useBulkActions: () => ({ runBulkDelete: vi.fn(), runBulkUpdate: vi.fn() }),
}));

vi.mock('../../components/BulkActionBar', () => ({
  default: () => null,
}));

vi.mock('../../components/LoadingSplash', () => ({
  default: () => null,
}));

vi.mock('framer-motion', async () => {
  const React = await import('react');
  return {
    motion: new Proxy({}, {
      get: (_target, prop) => {
        if (prop === Symbol.toStringTag) return 'motion';
        return (props: Record<string, unknown>) => React.createElement('div', props);
      },
    }),
    AnimatePresence: ({ children }: { children: ReactNode }) => children,
  };
});

const LONG_TITLE =
  'A very long risk title that is far too wide for the fixed Title column and must therefore be clamped to a single line while remaining readable through a tooltip';

const MATRIX: RiskMatrix = {
  severities: ['low', 'medium', 'high'],
  likelihoods: ['unlikely', 'possible', 'likely'],
  detections: [],
  bands: [],
  cells: [],
};

function mkRisk(overrides: Partial<Risk> = {}): Risk {
  return {
    id: 'RSK-1',
    title: '',
    failure_mode: '',
    effect: '',
    cause: '',
    description: '',
    severity: 'medium',
    likelihood: 'possible',
    probability: '',
    impact: '',
    mitigation: '',
    detection: '',
    linked_requirements: [],
    mitigating_requirements: [],
    linked_components: [],
    mitigating_components: [],
    status: 'open',
    created: '',
    modified: '',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/project/P1/risks']}>
      <Routes>
        <Route path="/project/:projectId/risks" element={<RisksPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getRiskMatrix).mockResolvedValue(MATRIX);
  vi.mocked(api.getRequirementTree).mockResolvedValue([]);
  vi.mocked(api.getComponentTree).mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

describe('RisksPage title column', () => {
  it('renders a title attribute equal to the full title on a long title', async () => {
    vi.mocked(api.listRisks).mockResolvedValue([mkRisk({ id: 'RSK-1', title: LONG_TITLE })]);

    renderPage();

    const cell = await screen.findByText(LONG_TITLE);
    expect(cell.className).toContain('line-clamp-1');
    expect(cell.getAttribute('title')).toBe(LONG_TITLE);
  });

  it('renders the placeholder and no title attribute when the title is missing', async () => {
    vi.mocked(api.listRisks).mockResolvedValue([mkRisk({ id: 'RSK-2', title: '' })]);

    const { container } = renderPage();

    await screen.findByText('RSK-2');
    const cell = container.querySelector('span.line-clamp-1');
    expect(cell).not.toBeNull();
    expect(cell!.textContent).toContain('—');
    expect(cell!.hasAttribute('title')).toBe(false);
  });

  it('gives the Title header cell a min-w- class', async () => {
    vi.mocked(api.listRisks).mockResolvedValue([mkRisk({ id: 'RSK-3', title: 'Short' })]);

    renderPage();

    const header = await screen.findByText('Title');
    const th = header.closest('th');
    expect(th).not.toBeNull();
    expect(th!.className).toContain('min-w-');
    expect(th!.className).toContain('14rem');
  });
});
