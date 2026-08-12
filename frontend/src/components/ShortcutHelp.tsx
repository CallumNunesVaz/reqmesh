import { X } from 'lucide-react';
import { LIST_ROUTES, DETAIL_ROUTES } from '../lib/keyboardShortcuts';
import Modal from './Modal';

interface ShortcutGroup { section: string; pages?: readonly string[]; items: { keys: string; description: string }[] }

const SHORTCUTS: ShortcutGroup[] = [
  {
    section: 'Global',
    items: [
      { keys: 'Ctrl+K', description: 'Open command palette' },
      { keys: 'Ctrl+E', description: 'Toggle edit / view mode' },
      { keys: 'Ctrl+G', description: 'Toggle graph pane' },
      { keys: 'Ctrl+H', description: 'Toggle guided mode (helpers)' },
      { keys: 'Ctrl+Z', description: 'Undo' },
      { keys: 'Ctrl+Y', description: 'Redo' },
      { keys: 'Ctrl+/ or ?', description: 'Show this help dialog' },
      { keys: 'F1', description: 'Open documentation' },
      { keys: 'Escape', description: 'Close dialog, deselect, or go back' },
    ],
  },
  {
    section: 'Quick Navigation',
    items: [
      { keys: 'Alt+R', description: 'Go to Requirements' },
      { keys: 'Alt+C', description: 'Go to Components' },
      { keys: 'Alt+S', description: 'Go to Specifications' },
      { keys: 'Alt+V', description: 'Go to Verification Cases' },
      { keys: 'Alt+T', description: 'Go to Trace Matrix' },
      { keys: 'Alt+H', description: 'Go to Change Requests' },
      { keys: 'Alt+K', description: 'Go to Risks' },
      { keys: 'Alt+B', description: 'Go to Baselines' },
      { keys: 'Alt+A', description: 'Go to Allocation' },
      { keys: 'Alt+M', description: 'Go to Metrics' },
      { keys: 'Alt+P', description: 'Go to Publish' },
    ],
  },
  {
    section: 'List Pages',
    pages: LIST_ROUTES,
    items: [
      { keys: 'j or ↓', description: 'Select next item' },
      { keys: 'k or ↑', description: 'Select previous item' },
      { keys: 'Enter', description: 'Open selected item' },
      { keys: '/', description: 'Focus the search field' },
      { keys: 'n', description: 'Create a new item' },
      { keys: 'Escape', description: 'Clear selection' },
    ],
  },
  {
    section: 'Detail Pages',
    pages: DETAIL_ROUTES,
    items: [
      { keys: 'Ctrl+S', description: 'Save changes' },
      { keys: 'Escape', description: 'Back to list' },
      { keys: 'Delete', description: 'Delete this item' },
    ],
  },
];

export default function ShortcutHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} closeOnEscape panelClassName="w-full max-w-lg max-h-[80vh] overflow-auto">
      <div className="flex items-center justify-between px-5 py-4 border-b">
        <h2 className="text-sm font-semibold text-card-foreground">Keyboard Shortcuts</h2>
        <button onClick={onClose} className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent">
          <X size={16} />
        </button>
      </div>
            <div className="p-5 space-y-5">
              {SHORTCUTS.map((group) => (
                <div key={group.section}>
                  <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">{group.section}</h3>
                  {group.pages && (
                    <p className="text-[10px] text-muted-foreground/60 mb-2 -mt-1 font-mono">{group.pages.join(' · ')}</p>
                  )}
                  <div className="space-y-1">
                    {group.items.map((item) => (
                      <div key={item.keys} className="flex items-center justify-between text-xs py-1 px-2 rounded hover:bg-accent/50">
                        <span className="text-card-foreground">{item.description}</span>
                        <span className="text-muted-foreground/70 font-mono bg-muted rounded-md px-1.5 py-0.5">{item.keys}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="px-5 py-3 border-t text-[10px] text-muted-foreground/50">
              Tip: shortcuts don't fire when you're typing in a text field (except save).
            </div>
    </Modal>
  );
}
