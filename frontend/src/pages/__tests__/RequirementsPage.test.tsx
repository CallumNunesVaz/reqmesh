/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import RequirementsPage from '../RequirementsPage';
import { useStore } from '../../store';
import { api } from '../../api/client';
import type { Requirement } from '../../api/client';

vi.mock('../../api/client', () => ({
  api: {
    listRequirements: vi.fn(),
    getEvaluation: vi.fn(),
    getProject: vi.fn(),
  },
  baselineNames: () => [],
  getTruncationInfo: () => null,
}));

vi.mock('../../store/auth', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ canEdit: () => false, user: { role: 'viewer' }, setEditMode: vi.fn() }),
}));

vi.mock('../../store/undo', () => ({
  useUndoStore: { getState: () => ({ push: vi.fn() }) },
}));

vi.mock('../../components/Layout', () => ({
  useSelectedReq: () => ({ selectedReqId: null, selectReq: vi.fn() }),
  useHoveredEntityBus: () => ({ set: vi.fn() }),
  useHoverHighlight: () => {},
}));

vi.mock('../../components/LoadingSplash', () => ({ default: () => null }));
vi.mock('../../components/RichTextEditor', () => ({ default: () => null }));
vi.mock('../../components/ConfirmDialog', () => ({ useConfirm: () => vi.fn() }));
vi.mock('../../lib/forceDelete', () => ({ deleteWithReferenceCheck: vi.fn() }));
vi.mock('../../components/Modal', () => ({ default: () => null }));
vi.mock('../../components/BulkActionBar', () => ({ default: () => null }));
vi.mock('../../components/AutocompleteInput', () => ({ default: () => null }));
vi.mock('../../components/Toast', () => ({ useToasts: () => ({ addToast: vi.fn() }) }));
vi.mock('../../components/TruncationBanner', () => ({ default: () => null }));
vi.mock('../../components/ReparentDialog', () => ({ default: () => null }));
vi.mock('../../components/CreateRequirementModal', () => ({ default: () => null }));
vi.mock('../../components/entities', () => ({ entityPath: () => null }));
vi.mock('../../components/TreeDragRow', () => ({
  DropRow: ({ children }: { children: ReactNode }) => children,
  DragGrip: () => null,
  TopLevelDropZone: () => null,
}));
vi.mock('../../hooks/useRangeSelection', () => ({
  useRangeSelection: () => ({
    selectedIds: new Set(),
    select: vi.fn(),
    setSelectedIds: vi.fn(),
    clear: vi.fn(),
  }),
}));
vi.mock('../../hooks/useTreeDrag', () => ({
  useTreeDrag: () => ({
    sensors: [],
    draggingIds: [],
    overId: null,
    dropIsValid: true,
    isDragging: false,
    dndHandlers: {},
    collisionDetection: undefined,
  }),
}));
vi.mock('@dnd-kit/core', () => ({
  DndContext: ({ children }: { children: ReactNode }) => children,
  DragOverlay: ({ children }: { children: ReactNode }) => children,
}));

function mkReq(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: 'REQ-1',
    type: 'functional',
    name: '',
    description: '',
    priority: 'medium',
    status: 'proposed',
    verification_method: '',
    verification_methods: [],
    attributes: [],
    parameters: [],
    constraints: [],
    relations: [],
    verification_cases: [],
    verification_status: 'pending',
    parent: null,
    cascade_from: null,
    rationale: '',
    source: '',
    allocated_to: '',
    baselines: [],
    references: [],
    reviewed: null,
    normative: false,
    priorities: {},
    needs: [],
    system_states: [],
    subject: null,
    created: '',
    modified: '',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/project/P1/requirements']}>
      <Routes>
        <Route path="/project/:projectId/requirements" element={<RequirementsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getEvaluation).mockResolvedValue({ requirements: [] } as never);
  vi.mocked(api.getProject).mockResolvedValue({
    baselines: [],
    stakeholders: [],
    system_states: [],
  } as never);
});

afterEach(() => {
  cleanup();
  useStore.setState({ requirements: [] });
});

describe('RequirementsPage row layout', () => {
  it('gives the description cell flex-1 and drops the fixed w-[28%] width', async () => {
    const req = mkReq({ id: 'REQ-1', name: 'Alpha', description: 'A description' });
    useStore.setState({ requirements: [req] });
    vi.mocked(api.listRequirements).mockResolvedValue([req] as never);

    renderPage();

    const cell = await screen.findByText('A description');
    expect(cell.className).toContain('flex-1');
    expect(cell.className).not.toContain('w-[28%]');
  });

  it('makes the name wrapper a bounded share at @3xl', async () => {
    const req = mkReq({ id: 'REQ-2', name: 'Beta', description: '' });
    useStore.setState({ requirements: [req] });
    vi.mocked(api.listRequirements).mockResolvedValue([req] as never);

    const { container } = renderPage();

    await screen.findByText('Beta');
    const nameWrapper = container.querySelector('[class*="@3xl:w-[38%]"]');
    expect(nameWrapper).not.toBeNull();
  });

  it('renders a title equal to the stripped description when non-empty', async () => {
    const req = mkReq({ id: 'REQ-3', name: 'Gamma', description: '<p>Hello <b>world</b></p>' });
    useStore.setState({ requirements: [req] });
    vi.mocked(api.listRequirements).mockResolvedValue([req] as never);

    renderPage();

    const cell = await screen.findByText('Hello world');
    expect(cell.getAttribute('title')).toBe('Hello world');
  });

  it('renders no title attribute when the description is empty', async () => {
    const req = mkReq({ id: 'REQ-4', name: 'Delta', description: '' });
    useStore.setState({ requirements: [req] });
    vi.mocked(api.listRequirements).mockResolvedValue([req] as never);

    const { container } = renderPage();

    await screen.findByText('Delta');
    const cell = container.querySelector('span.text-xs.truncate.min-w-0');
    expect(cell).not.toBeNull();
    expect(cell!.hasAttribute('title')).toBe(false);
  });
});
