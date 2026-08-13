import { useEditor, EditorContent, ReactNodeViewRenderer, NodeViewWrapper, type ReactNodeViewProps } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Image from '@tiptap/extension-image';
import CharacterCount from '@tiptap/extension-character-count';
import { Node } from '@tiptap/core';
import { nodeInputRule } from '@tiptap/core';
import { Bold, Italic, List, ListOrdered, Heading1, Undo2, Redo2 } from 'lucide-react';
import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { loadEntityIndex, useEntityKinds, type IndexedEntity } from './entityIndex';
import { ENTITY_META, entityIconMeta, entityPath, type EntityKind } from './entities';
import { findMentionTrigger } from './mentions';
import MentionPicker from './MentionPicker';

interface RichTextEditorProps {
  content: string;
  onChange: (html: string) => void;
  onBlur: (html: string) => void;
  disabled?: boolean;
  placeholder?: string;
  id?: string;
}

const ENTITY_LINK_GLOBAL_REGEX = /\[\[([\w\-_.]+)\]\]/g;
const ENTITY_LINK_INPUT_REGEX = /\[\[([\w\-_.]+)\]\]$/;

function preprocessContent(html: string): string {
  // Avoid double-wrapping: split on existing <span data-entity-id> blocks,
  // only apply the regex to the text between them.
  const parts = html.split(/(<span data-entity-id="[^"]*">.*?<\/span>)/gs);
  return parts.map((part, i) => {
    if (i % 2 === 0) {
      return part.replace(ENTITY_LINK_GLOBAL_REGEX, '<span data-entity-id="$1">[[$1]]</span>');
    }
    return part;
  }).join('');
}

/**
 * How an entity link looks *while editing*.
 *
 * `renderHTML` below still emits `<span data-entity-id>[[ID]]</span>` — that is
 * the stored form and it is deliberately unchanged, so nothing downstream (the
 * YAML, the exports, the read-mode renderer) has to learn a new format. This
 * node view only replaces what the author sees with the same icon-and-id chip
 * the rest of the app uses for a reference.
 */
function EntityLinkNodeView({ node }: ReactNodeViewProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const kinds = useEntityKinds(projectId);
  const id: string = node.attrs.entityId;
  const kind = kinds.get(id);
  const meta = entityIconMeta(kind ?? 'requirement');
  const Icon = meta.icon;

  return (
    <NodeViewWrapper as="span" className="inline-flex items-baseline">
      <span
        data-entity-id={id}
        contentEditable={false}
        title={kind ? `${ENTITY_META[kind].label} ${id}` : `Unknown entity ${id}`}
        className={`inline-flex items-center gap-1 align-baseline rounded px-1 py-px mx-px
          font-mono text-[0.9em] cursor-pointer border
          ${kind ? 'bg-accent/60 border-border' : 'bg-cs-orange/10 border-cs-orange/40'}`}
      >
        <Icon size={11} className={`shrink-0 ${kind ? meta.cls : 'text-cs-orange'}`} />
        {id}
      </span>
    </NodeViewWrapper>
  );
}

const EntityLinkExtension = Node.create({
  name: 'entityLink',
  inline: true,
  group: 'inline',
  atom: true,

  addNodeView() {
    return ReactNodeViewRenderer(EntityLinkNodeView);
  },

  addAttributes() {
    return {
      entityId: {
        default: null,
        // Without an explicit parseHTML the attribute is never read back out of
        // the DOM, so every node restored from stored content came back with
        // entityId === null: the chip could not name its entity and the click
        // handler had no id to navigate to. Only freshly typed links worked.
        parseHTML: (element) => element.getAttribute('data-entity-id'),
        renderHTML: (attributes) =>
          (attributes.entityId ? { 'data-entity-id': attributes.entityId } : {}),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-entity-id]' }];
  },

  // `node.attrs`, not `HTMLAttributes`: the latter is the *rendered* attribute
  // map, where the id now appears as `data-entity-id`, so reading `.entityId`
  // off it yields undefined and serialises the link as `[[undefined]]`.
  renderHTML({ node, HTMLAttributes }) {
    const id = node.attrs.entityId;
    return ['span', {
      ...HTMLAttributes,
      class: 'text-blue-500 underline cursor-pointer',
    }, `[[${id}]]`];
  },

  addInputRules() {
    return [
      nodeInputRule({
        find: ENTITY_LINK_INPUT_REGEX,
        type: this.type,
        getAttributes: (match) => ({ entityId: match[1] }),
      }),
    ];
  },
});

export default function RichTextEditor({ content, onChange, onBlur, disabled = false, placeholder, id }: RichTextEditorProps) {
  const isInternalChange = useRef(false);
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const entityKinds = useEntityKinds(projectId);

  // ── @-mention state ────────────────────────────────────────────────────
  // `mention` holds the document range the `@query` occupies plus the caret
  // rectangle to anchor the picker to. Focus never leaves the editor, so the
  // highlighted index and the result list live here rather than in the picker.
  const [entities, setEntities] = useState<IndexedEntity[]>([]);
  const [mention, setMention] = useState<{ query: string; from: number; to: number; rect: DOMRect } | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const mentionResults = useRef<IndexedEntity[]>([]);
  // `editorProps` is captured once when the editor is created, so its key
  // handler cannot read the state above directly — it would see the values from
  // first render forever. These refs are the bridge.
  const mentionOpen = useRef(false);
  const mentionIndexRef = useRef(0);
  const insertMention = useRef<((entity: IndexedEntity) => void) | null>(null);

  useEffect(() => { mentionOpen.current = mention !== null; }, [mention]);
  useEffect(() => { mentionIndexRef.current = mentionIndex; }, [mentionIndex]);

  useEffect(() => {
    if (!projectId || disabled) return;
    let live = true;
    loadEntityIndex(projectId).then((list) => { if (live) setEntities(list); });
    return () => { live = false; };
  }, [projectId, disabled]);

  const processedContent = preprocessContent(content || '');

  const handleEditorClick = useCallback((e: React.MouseEvent) => {
    let target = e.target as HTMLElement | null;
    while (target && target !== e.currentTarget) {
      const entityId = target.getAttribute('data-entity-id');
      if (entityId && projectId) {
        e.preventDefault();
        e.stopPropagation();
        const kind: EntityKind = entityKinds.get(entityId) ?? 'requirement';
        // A mention of a kind with no page of its own swallows the click
        // rather than navigating somewhere arbitrary.
        const destination = entityPath(kind, projectId, entityId);
        if (destination) navigate(destination);
        return;
      }
      target = target.parentElement;
    }
  }, [navigate, projectId, entityKinds]);

  /**
   * Recompute the active mention from the text preceding the caret.
   *
   * Only the current text block is scanned, so an `@` in the paragraph above
   * cannot reach across a block boundary. `textBetween` is given a one-character
   * placeholder for leaf nodes, which keeps string offsets aligned with document
   * positions inside the block — without it, an image or an existing entity chip
   * earlier in the line would shift the replacement range.
   */
  const detectMention = useCallback((ed: NonNullable<typeof editor>) => {
    const { state } = ed;
    const { from, empty } = state.selection;
    if (!empty) { setMention(null); return; }

    const blockStart = state.doc.resolve(from).start();
    const textBefore = state.doc.textBetween(blockStart, from, '\n', '￼');
    const trigger = findMentionTrigger(textBefore, textBefore.length);
    if (!trigger) { setMention(null); return; }

    const docFrom = from - (textBefore.length - trigger.from);
    const coords = ed.view.coordsAtPos(from);
    setMention({
      query: trigger.query,
      from: docFrom,
      to: from,
      rect: new DOMRect(coords.left, coords.top, 0, coords.bottom - coords.top),
    });
    setMentionIndex(0);
  }, []);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Placeholder.configure({
        placeholder: placeholder ?? 'Write a description…',
      }),
      Image.configure({
        inline: true,
      }),
      CharacterCount.configure({}),
      EntityLinkExtension,
    ],
    editorProps: {
      // The picker has no focus, so its keys have to be intercepted here —
      // before ProseMirror treats Enter as a paragraph break or the arrows as
      // cursor movement.
      handleKeyDown(_view, event) {
        if (!mentionOpen.current) return false;
        const count = mentionResults.current.length;
        if (event.key === 'Escape') { setMention(null); return true; }
        if (count === 0) return false;
        if (event.key === 'ArrowDown') {
          setMentionIndex((i) => (i + 1) % count);
          return true;
        }
        if (event.key === 'ArrowUp') {
          setMentionIndex((i) => (i - 1 + count) % count);
          return true;
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
          const picked = mentionResults.current[mentionIndexRef.current];
          if (picked) { insertMention.current?.(picked); return true; }
        }
        return false;
      },
      transformPastedHTML(html: string) {
        return html
          .replace(/<meta[^>]*>/gi, '')
          .replace(/<o:[^>]+>[^<]*<\/o:[^>]+>/gi, '')
          .replace(/<!--[\s\S]*?-->/g, '')
          .replace(/\s*(class|style|lang|width|height|align|valign|bgcolor|border|cellpadding|cellspacing|mso-[a-z-]+|xml:[a-z]+)=["'][^"']*["']/gi, '')
          .replace(/<font[^>]*>/gi, '')
          .replace(/<\/font>/gi, '')
          .replace(/<span[^>]*>/gi, '<span>')
          .replace(/<(\w+)\s+>/g, '<$1>');
      },
    },
    content: processedContent,
    editable: !disabled,
    onUpdate: ({ editor }) => {
      isInternalChange.current = true;
      onChange(editor.getHTML());
      detectMention(editor);
    },
    onSelectionUpdate: ({ editor }) => detectMention(editor),
    onBlur: ({ editor }) => {
      // Selecting from the picker is a mousedown, which fires before blur, so
      // tearing the mention down here cannot swallow a click.
      setMention(null);
      onBlur(editor.getHTML());
    },
  });

  useEffect(() => {
    if (editor) {
      editor.setEditable(!disabled);
    }
  }, [disabled, editor]);

  // Replace the `@query` range with an entity-link node. A trailing space keeps
  // typing flowing — without it the caret sits welded to an atom node and the
  // next character is fiddly to place.
  const handleMentionSelect = useCallback((entity: IndexedEntity) => {
    if (!editor || !mention) return;
    editor.chain().focus()
      .insertContentAt({ from: mention.from, to: mention.to }, [
        { type: 'entityLink', attrs: { entityId: entity.id } },
        { type: 'text', text: ' ' },
      ])
      .run();
    setMention(null);
  }, [editor, mention]);

  useEffect(() => { insertMention.current = handleMentionSelect; }, [handleMentionSelect]);

  useEffect(() => {
    if (isInternalChange.current) {
      isInternalChange.current = false;
      return;
    }
    // Preprocess here too, not just at mount. Feeding the raw value back in
    // undid the `[[ID]]` → <span data-entity-id> wrapping the editor was built
    // with, so a *stored* reference collapsed to literal bracket text the
    // moment this effect ran and only freshly-typed ones ever became chips.
    // Comparing the processed form also stops the effect fighting itself:
    // getHTML() emits the span form, so the two match once they agree.
    const processed = preprocessContent(content || '');
    if (editor && processed !== editor.getHTML()) {
      editor.commands.setContent(processed, { emitUpdate: false });
    }
  }, [content, editor]);

  if (!editor) {
    return <div id={id} className="input min-h-[100px]" />;
  }

  const ToolbarButton = ({ active, onClick, label, children }: { active?: boolean; onClick: () => void; label: string; children: React.ReactNode }) => (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`p-1.5 rounded transition-colors ${
        active
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:text-foreground hover:bg-accent'
      }`}
    >
      {children}
    </button>
  );

  return (
    <>
      {/* The onClick is click-delegation for the [[ID]] mention chips rendered
          inside the contenteditable; the wrapper is not itself a control and the
          chips cannot be real links without changing the stored format. */}
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events */}
      <div className={`border rounded-lg overflow-hidden ${!disabled ? 'focus-within:ring-2 focus-within:ring-ring/20 focus-within:border-ring/30' : 'opacity-70'} transition-all`} onClick={handleEditorClick}>
      {!disabled && (
      <div className="flex items-center gap-0.5 px-2 py-1.5 border-b bg-muted/50">
        <ToolbarButton label="Bold" active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()}>
          <Bold size={15} />
        </ToolbarButton>
        <ToolbarButton label="Italic" active={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()}>
          <Italic size={15} />
        </ToolbarButton>
        <div className="w-px h-4 bg-border mx-1" />
        <ToolbarButton label="Heading" active={editor.isActive('heading', { level: 1 })} onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}>
          <Heading1 size={15} />
        </ToolbarButton>
        <ToolbarButton label="Bullet List" active={editor.isActive('bulletList')} onClick={() => editor.chain().focus().toggleBulletList().run()}>
          <List size={15} />
        </ToolbarButton>
        <ToolbarButton label="Ordered List" active={editor.isActive('orderedList')} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
          <ListOrdered size={15} />
        </ToolbarButton>
        <div className="flex-1" />
        <ToolbarButton label="Undo" onClick={() => editor.chain().focus().undo().run()}>
          <Undo2 size={15} />
        </ToolbarButton>
        <ToolbarButton label="Redo" onClick={() => editor.chain().focus().redo().run()}>
          <Redo2 size={15} />
        </ToolbarButton>
        </div>
      )}
      <EditorContent
        editor={editor}
        id={id}
        className="prose prose-sm dark:prose-invert max-w-none p-3 min-h-[120px] focus:outline-none
          [&_.ProseMirror]:outline-none [&_.ProseMirror]:min-h-[100px]
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:text-muted-foreground
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:content-[attr(data-placeholder)]
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:float-left
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:pointer-events-none"
      />
      {mention && !disabled && (
        <MentionPicker
          entities={entities}
          query={mention.query}
          anchor={mention.rect}
          activeIndex={mentionIndex}
          onSelect={handleMentionSelect}
          onResults={(r) => { mentionResults.current = r; }}
        />
      )}
      {!disabled && (
        <div className="px-3 py-1 border-t text-[10px] text-muted-foreground/50 flex justify-end">
          {editor.storage.characterCount.words()} words · {editor.storage.characterCount.characters()} chars
          <span className="ml-auto">Type <kbd className="font-mono">@</kbd> to link an entity</span>
        </div>
      )}
    </div>
    </>
  );
}
