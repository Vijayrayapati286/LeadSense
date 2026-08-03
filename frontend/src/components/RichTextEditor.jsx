import { useEffect, useRef } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import { TextStyle, FontSize } from '@tiptap/extension-text-style';
import Color from '@tiptap/extension-color';
import FontFamily from '@tiptap/extension-font-family';
import TextAlign from '@tiptap/extension-text-align';
import Link from '@tiptap/extension-link';
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Image from '@tiptap/extension-image';
import Highlight from '@tiptap/extension-highlight';
import Placeholder from '@tiptap/extension-placeholder';
import DOMPurify from 'dompurify';
import {
  FiBold, FiItalic, FiUnderline, FiAlignLeft, FiAlignCenter, FiAlignRight,
  FiAlignJustify, FiList, FiLink2, FiTable, FiMinus, FiRotateCcw, FiRotateCw,
  FiType, FiChevronsRight, FiChevronsLeft,
} from 'react-icons/fi';

// Kept in sync with backend/app/utils/helpers.py's sanitize_html allowlist —
// this is defense-in-depth for the in-app preview; the server re-sanitizes
// on save regardless, since the client can't be trusted.
const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'span', 'div', 'ul', 'ol', 'li', 'a',
  'table', 'thead', 'tbody', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'blockquote', 'hr', 'img', 'sub', 'sup',
];
const ALLOWED_ATTR = ['style', 'href', 'target', 'rel', 'src', 'alt', 'width', 'height', 'colspan', 'rowspan'];

function purify(html) {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|data:image\/)/i,
  });
}

/** Strip Word/Outlook-only paste cruft (conditional comments, mso-* style
 * declarations, Mso* classes, o:/w:/v: namespaced tags) before it ever
 * reaches TipTap's parser, so a paste from Outlook/Word doesn't leave
 * `mso-fareast-font-family: ...` litter or empty `<o:p>` elements behind. */
function sanitizePastedHtml(html) {
  if (!html) return html;

  const withoutComments = html.replace(/<!--[\s\S]*?-->/g, '');
  const doc = new DOMParser().parseFromString(withoutComments, 'text/html');

  doc.querySelectorAll('script, style, meta, link').forEach((el) => el.remove());

  doc.querySelectorAll('*').forEach((el) => {
    // Namespaced Word/Outlook elements (o:p, w:sectPr, v:shape, ...) parse as
    // literal tag names in an HTML document — unwrap them, keep their content.
    if (/^[a-z]+:/i.test(el.tagName)) {
      el.replaceWith(...el.childNodes);
      return;
    }

    const style = el.getAttribute('style');
    if (style) {
      const kept = style
        .split(';')
        .map((decl) => decl.trim())
        .filter((decl) => decl && !/^mso-/i.test(decl))
        .join('; ');
      if (kept) el.setAttribute('style', kept);
      else el.removeAttribute('style');
    }

    const cls = el.getAttribute('class');
    if (cls && /(^|\s)Mso\w+/i.test(cls)) {
      const kept = cls.split(/\s+/).filter((c) => c && !/^Mso/i.test(c)).join(' ');
      if (kept) el.setAttribute('class', kept);
      else el.removeAttribute('class');
    }

    el.removeAttribute('lang');
  });

  return doc.body.innerHTML;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// An <img> src that isn't already a URL we can use — e.g. Outlook/Word's
// `cid:...` references into the original message, or a `file:///C:\Users\...`
// path into a temp folder on the sender's machine. Neither means anything to
// a browser rendering the pasted content elsewhere.
const UNRESOLVABLE_IMG_SRC_RE = /(<img\b[^>]*\bsrc=")(?!https?:|data:image\/)[^"]*(")/gi;

/** Handles every paste that carries HTML ourselves via `editor.commands.
 * insertContent`, instead of letting ProseMirror's native clipboard-to-slice
 * conversion run (the path `transformPastedHTML` normally feeds into).
 * That native path silently drops inline image nodes pasted via HTML — it's
 * a real discrepancy from `insertContent`, confirmed by direct testing, not
 * a schema or sanitizer issue — so we bypass it entirely and always build
 * the final HTML ourselves before inserting it.
 *
 * Also substitutes real pixels in for any unresolvable <img src> (Outlook's
 * `cid:...`, or a `file:///...` path) when Windows also put the actual
 * bitmap on the clipboard as a separate file — Chrome exposes that via
 * `clipboardData.items`.
 *
 * A screenshot tool's "Copy" (Snipping Tool, Win+Shift+S, etc.) puts *only*
 * image bytes on the clipboard — no text/html at all — which is a distinct
 * case from a plain-text paste even though both lack HTML: there's nothing
 * for ProseMirror's default paste conversion to build a slice from, so
 * without handling it explicitly here the image is silently dropped and
 * nothing is inserted, with no error shown. Falls through to default paste
 * handling (returns false) only when there's neither HTML nor an image file
 * — i.e. an actual plain-text paste. */
function handlePasteContent(editorRef, event) {
  const html = event.clipboardData?.getData('text/html');
  const items = event.clipboardData?.items;
  const imageFiles = items
    ? Array.from(items)
        .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
        .map((item) => item.getAsFile())
        .filter(Boolean)
    : [];

  if (!html && imageFiles.length === 0) return false;

  event.preventDefault();

  if (!html) {
    Promise.all(imageFiles.map(readFileAsDataUrl)).then((dataUrls) => {
      const editor = editorRef.current;
      if (!editor) return;
      const imgHtml = dataUrls.map((url) => `<img src="${url}">`).join('');
      editor.chain().focus().insertContent(purify(imgHtml)).run();
    });
    return true;
  }

  const insert = (dataUrls) => {
    const editor = editorRef.current;
    if (!editor) return;
    let i = 0;
    const withImages = sanitizePastedHtml(html).replace(UNRESOLVABLE_IMG_SRC_RE, (match, before, after) => {
      const dataUrl = dataUrls[i++];
      return dataUrl ? `${before}${dataUrl}${after}` : match;
    });
    editor.chain().focus().insertContent(purify(withImages)).run();
  };

  if (imageFiles.length > 0) {
    Promise.all(imageFiles.map(readFileAsDataUrl)).then(insert);
  } else {
    insert([]);
  }

  return true;
}

const FONT_FAMILIES = [
  'Arial',
  'Calibri',
  'Cambria',
  'Courier New',
  'Garamond',
  'Georgia',
  'Helvetica',
  'Impact',
  'Lucida Sans',
  'Palatino',
  'Segoe UI',
  'Tahoma',
  'Times New Roman',
  'Trebuchet MS',
  'Verdana',
];
const FONT_SIZES = ['10px', '12px', '14px', '16px', '18px', '20px', '24px', '28px', '32px'];

function ToolbarButton({ onClick, active, disabled, title, children }) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={`p-1.5 rounded hover:bg-gray-200 disabled:opacity-30 disabled:hover:bg-transparent transition-colors ${
        active ? 'bg-primary-100 text-primary-700' : 'text-gray-600'
      }`}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="w-px h-5 bg-gray-300 mx-1" />;
}

function Toolbar({ editor }) {
  if (!editor) return null;

  const setLink = () => {
    const previousUrl = editor.getAttributes('link').href;
    const url = window.prompt('Link URL', previousUrl || 'https://');
    if (url === null) return;
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: url, target: '_blank', rel: 'noopener noreferrer' }).run();
  };

  const insertTable = () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
  const inTable = editor.isActive('table');

  return (
    <div className="flex flex-wrap items-center gap-0.5 px-2 py-1.5 border-b border-gray-300 bg-gray-50 rounded-t-lg">
      <select
        title="Font family"
        className="text-xs border border-gray-200 rounded px-1 py-1 bg-white max-w-[110px]"
        value={editor.getAttributes('textStyle').fontFamily || ''}
        onChange={(e) => {
          const v = e.target.value;
          if (v) editor.chain().focus().setFontFamily(v).run();
          else editor.chain().focus().unsetFontFamily().run();
        }}
      >
        <option value="">Font</option>
        {FONT_FAMILIES.map((f) => (
          <option key={f} value={f} style={{ fontFamily: f }}>{f}</option>
        ))}
      </select>

      <select
        title="Font size"
        className="text-xs border border-gray-200 rounded px-1 py-1 bg-white max-w-[70px]"
        value={editor.getAttributes('textStyle').fontSize || ''}
        onChange={(e) => {
          const v = e.target.value;
          if (v) editor.chain().focus().setFontSize(v).run();
          else editor.chain().focus().unsetFontSize().run();
        }}
      >
        <option value="">Size</option>
        {FONT_SIZES.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>

      <Divider />

      <ToolbarButton title="Bold" active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()}>
        <FiBold size={14} />
      </ToolbarButton>
      <ToolbarButton title="Italic" active={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()}>
        <FiItalic size={14} />
      </ToolbarButton>
      <ToolbarButton title="Underline" active={editor.isActive('underline')} onClick={() => editor.chain().focus().toggleUnderline().run()}>
        <FiUnderline size={14} />
      </ToolbarButton>
      <ToolbarButton title="Strikethrough" active={editor.isActive('strike')} onClick={() => editor.chain().focus().toggleStrike().run()}>
        <span className="text-xs font-bold line-through px-0.5">S</span>
      </ToolbarButton>

      <label title="Text color" className="p-1.5 rounded hover:bg-gray-200 cursor-pointer flex items-center">
        <FiType size={14} className="text-gray-600" />
        <input
          type="color"
          className="w-3 h-3 ml-0.5 cursor-pointer align-middle"
          value={editor.getAttributes('textStyle').color || '#000000'}
          onChange={(e) => editor.chain().focus().setColor(e.target.value).run()}
        />
      </label>
      <label title="Highlight color" className="p-1.5 rounded hover:bg-gray-200 cursor-pointer flex items-center">
        <span className="text-xs font-bold px-0.5 bg-yellow-200 rounded-sm">H</span>
        <input
          type="color"
          className="w-3 h-3 ml-0.5 cursor-pointer align-middle"
          value="#fff59d"
          onChange={(e) => editor.chain().focus().toggleHighlight({ color: e.target.value }).run()}
        />
      </label>

      <Divider />

      <ToolbarButton title="Align left" active={editor.isActive({ textAlign: 'left' })} onClick={() => editor.chain().focus().setTextAlign('left').run()}>
        <FiAlignLeft size={14} />
      </ToolbarButton>
      <ToolbarButton title="Align center" active={editor.isActive({ textAlign: 'center' })} onClick={() => editor.chain().focus().setTextAlign('center').run()}>
        <FiAlignCenter size={14} />
      </ToolbarButton>
      <ToolbarButton title="Align right" active={editor.isActive({ textAlign: 'right' })} onClick={() => editor.chain().focus().setTextAlign('right').run()}>
        <FiAlignRight size={14} />
      </ToolbarButton>
      <ToolbarButton title="Justify" active={editor.isActive({ textAlign: 'justify' })} onClick={() => editor.chain().focus().setTextAlign('justify').run()}>
        <FiAlignJustify size={14} />
      </ToolbarButton>

      <Divider />

      <ToolbarButton title="Bulleted list" active={editor.isActive('bulletList')} onClick={() => editor.chain().focus().toggleBulletList().run()}>
        <FiList size={14} />
      </ToolbarButton>
      <ToolbarButton title="Numbered list" active={editor.isActive('orderedList')} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
        <span className="text-xs font-bold px-0.5">1.</span>
      </ToolbarButton>
      <ToolbarButton title="Decrease indent" disabled={!editor.can().liftListItem('listItem')} onClick={() => editor.chain().focus().liftListItem('listItem').run()}>
        <FiChevronsLeft size={14} />
      </ToolbarButton>
      <ToolbarButton title="Increase indent" disabled={!editor.can().sinkListItem('listItem')} onClick={() => editor.chain().focus().sinkListItem('listItem').run()}>
        <FiChevronsRight size={14} />
      </ToolbarButton>

      <Divider />

      <ToolbarButton title="Insert/edit link" active={editor.isActive('link')} onClick={setLink}>
        <FiLink2 size={14} />
      </ToolbarButton>
      <ToolbarButton title="Insert table" onClick={insertTable}>
        <FiTable size={14} />
      </ToolbarButton>
      {inTable && (
        <>
          <ToolbarButton title="Add row" onClick={() => editor.chain().focus().addRowAfter().run()}>
            <span className="text-[10px] font-semibold px-0.5">+Row</span>
          </ToolbarButton>
          <ToolbarButton title="Add column" onClick={() => editor.chain().focus().addColumnAfter().run()}>
            <span className="text-[10px] font-semibold px-0.5">+Col</span>
          </ToolbarButton>
          <ToolbarButton title="Delete row" onClick={() => editor.chain().focus().deleteRow().run()}>
            <span className="text-[10px] font-semibold px-0.5">-Row</span>
          </ToolbarButton>
          <ToolbarButton title="Delete column" onClick={() => editor.chain().focus().deleteColumn().run()}>
            <span className="text-[10px] font-semibold px-0.5">-Col</span>
          </ToolbarButton>
          <ToolbarButton title="Delete table" onClick={() => editor.chain().focus().deleteTable().run()}>
            <span className="text-[10px] font-semibold px-0.5">Del</span>
          </ToolbarButton>
        </>
      )}
      <ToolbarButton title="Horizontal line" onClick={() => editor.chain().focus().setHorizontalRule().run()}>
        <FiMinus size={14} />
      </ToolbarButton>

      <Divider />

      <ToolbarButton title="Undo" disabled={!editor.can().undo()} onClick={() => editor.chain().focus().undo().run()}>
        <FiRotateCcw size={14} />
      </ToolbarButton>
      <ToolbarButton title="Redo" disabled={!editor.can().redo()} onClick={() => editor.chain().focus().redo().run()}>
        <FiRotateCw size={14} />
      </ToolbarButton>
      <ToolbarButton title="Clear formatting" onClick={() => editor.chain().focus().clearNodes().unsetAllMarks().run()}>
        <span className="text-xs font-semibold px-0.5">Tx</span>
      </ToolbarButton>
    </div>
  );
}

/** Outlook-style WYSIWYG editor for Manual template bodies. Stores/emits real
 * HTML (via onChange) instead of the plain markdown-lite subset the
 * placeholder/AI template types still use. */
export default function RichTextEditor({ value, onChange, placeholder }) {
  const editorRef = useRef(null);

  const editor = useEditor({
    extensions: [
      // StarterKit v3 bundles its own Link and Underline by default now —
      // disable those so our separately-configured instances below (with
      // custom options) don't collide with them under the same name.
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: false, underline: false }),
      Underline,
      TextStyle,
      FontSize,
      Color,
      FontFamily,
      Highlight.configure({ multicolor: true }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Link.configure({ openOnClick: false, autolink: true }),
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
      // `inline: true` — signature/web images are almost always embedded
      // inline (inside a link, inside a paragraph, inside a table cell), and
      // a block-only image node can't be placed at an inline position.
      // `allowBase64: true` — the extension's default DOM-parse rule is
      // literally `img[src]:not([src^="data:"])`, i.e. it silently ignores
      // every data: URI image. Since pasted images are embedded as base64
      // data URIs (see handlePasteContent below), every one of them was
      // being dropped without this.
      Image.configure({ inline: true, allowBase64: true }),
      Placeholder.configure({ placeholder: placeholder || 'Write your email content here. Use {{Name}}, {{Company}} for personalization.' }),
    ],
    content: value || '',
    editorProps: {
      attributes: { class: 'rich-text-content' },
      // handlePasteContent intercepts and inserts HTML paste itself (see
      // its doc comment for why); transformPastedHTML is unused as a result
      // but left absent rather than kept as dead config.
      handlePaste: (_view, event) => handlePasteContent(editorRef, event),
    },
    onUpdate: ({ editor: ed }) => onChange(ed.getHTML()),
  });

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  // Reload editor content when the parent swaps in a different template's
  // body (switching templates/mailers, or the Manual-compose default
  // signature landing the moment it's auto-filled) — but not on every
  // keystroke, since onUpdate above already keeps `value` equal to the live
  // doc. Parking the cursor at the very start each time means the compose
  // window is immediately ready to type into, rather than requiring a click
  // above whatever content just got loaded in (e.g. the default signature).
  useEffect(() => {
    if (!editor) return;
    const current = editor.getHTML();
    const next = value || '';
    if (next !== current) {
      editor.commands.setContent(next, false);
      editor.commands.focus('start');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, editor]);

  if (!editor) return null;

  return (
    <div className="border border-gray-300 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-primary-500 focus-within:border-transparent">
      <Toolbar editor={editor} />
      <EditorContent editor={editor} className="min-h-[220px] max-h-[480px] overflow-y-auto px-3 py-2 text-sm" />
    </div>
  );
}
