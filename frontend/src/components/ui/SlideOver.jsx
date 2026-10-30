import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { FiX } from 'react-icons/fi';

export default function SlideOver({ isOpen, onClose, title, subtitle, children, width = 'md', plain = false }) {
  useEffect(() => {
    if (!isOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKey);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const widths = {
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-2xl',
    '3xl': 'max-w-4xl',
    full: 'max-w-5xl',
  };

  return createPortal(
    <div
      className="fixed inset-y-0 right-0 z-50 flex justify-end"
      style={{ left: 'var(--app-sidebar, 0px)' }}
    >
      <div className="absolute inset-0 bg-slate-900/45 backdrop-blur-[1px]" onClick={onClose} aria-hidden />
      <aside
        className={`relative flex h-full w-full ${widths[width] || widths.md} flex-col bg-white shadow-2xl ${plain ? '' : 'animate-fade-in'}`}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : 'Details'}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-gray-100 bg-white px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
            {subtitle ? <p className="mt-0.5 text-sm text-gray-500">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100"
            aria-label="Close"
          >
            <FiX size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto bg-white px-5 py-4">{children}</div>
      </aside>
    </div>,
    document.body,
  );
}
