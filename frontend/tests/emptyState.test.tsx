/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { LogIn } from 'lucide-react';
import EmptyState from '../src/components/EmptyState';

afterEach(cleanup);

describe('EmptyState', () => {
  it('renders the title', () => {
    render(<EmptyState title="No requirements yet" />);
    expect(screen.queryByText('No requirements yet')).not.toBeNull();
  });

  it('renders the hint only when supplied', () => {
    const { rerender } = render(<EmptyState title="Title" />);
    expect(screen.queryByText('A helpful hint')).toBeNull();

    rerender(<EmptyState title="Title" hint="A helpful hint" />);
    expect(screen.queryByText('A helpful hint')).not.toBeNull();
  });

  it('renders the action button and calls onClick when clicked; renders no button when action is absent', () => {
    const onClick = vi.fn();
    const { rerender } = render(
      <EmptyState title="Title" action={{ label: 'New Requirement', onClick }} />,
    );

    const button = screen.getByRole('button', { name: 'New Requirement' });
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);

    rerender(<EmptyState title="Title" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders the card class by default and omits it for variant="bare"', () => {
    const { container, rerender } = render(<EmptyState title="Title" />);
    expect(container.firstElementChild!.className.split(/\s+/)).toContain('card');

    rerender(<EmptyState variant="bare" title="Title" />);
    expect(container.firstElementChild!.className.split(/\s+/)).not.toContain('card');
  });

  it('marks the icon aria-hidden', () => {
    const { container } = render(<EmptyState icon={LogIn} title="Title" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg!.getAttribute('aria-hidden')).toBe('true');
  });

  it('renders children below the hint', () => {
    const { container } = render(
      <EmptyState title="Title" hint="A helpful hint">
        <button>Clear filters</button>
      </EmptyState>,
    );

    const hint = container.querySelector('p.text-sm');
    const child = container.querySelector('button');
    expect(hint).not.toBeNull();
    expect(child).not.toBeNull();
    expect(
      (hint!.compareDocumentPosition(child!) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
    ).toBe(true);
  });
});
