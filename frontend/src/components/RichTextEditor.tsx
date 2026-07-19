import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Image from '@tiptap/extension-image';
import CharacterCount from '@tiptap/extension-character-count';
import { Bold, Italic, List, ListOrdered, Heading1, Undo2, Redo2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

interface RichTextEditorProps {
  content: string;
  onChange: (html: string) => void;
  onBlur: (html: string) => void;
  disabled?: boolean;
}

export default function RichTextEditor({ content, onChange, onBlur, disabled = false }: RichTextEditorProps) {
  const isInternalChange = useRef(false);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Placeholder.configure({
        placeholder: 'Write your requirement description...',
      }),
      Image.configure({
        inline: true,
      }),
      CharacterCount.configure({}),
    ],
    editorProps: {
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
    content: content || '',
    editable: !disabled,
    onUpdate: ({ editor }) => {
      isInternalChange.current = true;
      onChange(editor.getHTML());
    },
    onBlur: ({ editor }) => {
      onBlur(editor.getHTML());
    },
  });

  useEffect(() => {
    if (editor) {
      editor.setEditable(!disabled);
    }
  }, [disabled, editor]);

  useEffect(() => {
    if (isInternalChange.current) {
      isInternalChange.current = false;
      return;
    }
    if (editor && content !== editor.getHTML()) {
      editor.commands.setContent(content || '', false);
    }
  }, [content, editor]);

  if (!editor) {
    return <div className="input min-h-[100px]" />;
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
    <div className={`border rounded-lg overflow-hidden ${!disabled ? 'focus-within:ring-2 focus-within:ring-ring/20 focus-within:border-ring/30' : 'opacity-70'} transition-all`}>
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
        className="prose prose-sm dark:prose-invert max-w-none p-3 min-h-[120px] focus:outline-none
          [&_.ProseMirror]:outline-none [&_.ProseMirror]:min-h-[100px]
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:text-muted-foreground
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:content-[attr(data-placeholder)]
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:float-left
          [&_.ProseMirror_p.is-editor-empty:first-child::before]:pointer-events-none"
      />
      {!disabled && (
        <div className="px-3 py-1 border-t text-[10px] text-muted-foreground/50 flex justify-end">
          {editor.storage.characterCount.words()} words · {editor.storage.characterCount.characters()} chars
        </div>
      )}
    </div>
  );
}
