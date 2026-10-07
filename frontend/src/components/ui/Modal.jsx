import { useEffect, useId, useRef } from 'react';
import { FiX } from 'react-icons/fi';

export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  hideHeader = false,
  level = 'base',
}) {
  const titleId = useId();
  const dialogRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      requestAnimationFrame(() => dialogRef.current?.focus());
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sizes = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
  };

  return (
    <div
      className={`fixed inset-y-0 right-0 ${level === 'top' ? 'z-[80]' : 'z-50'} flex items-center justify-center p-4 transition-[left] duration-300`}
      style={{ left: 'var(--app-sidebar, 16rem)' }}
    >
      {/* Cover only the area beside the sidebar so the card centers there. */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-md" onClick={onClose} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        className={`relative w-full ${sizes[size]} max-h-[90vh] overflow-y-auto rounded-3xl bg-white shadow-2xl outline-none animate-rise-in [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden`}
      >
        {!hideHeader && (
          <div className="flex items-center justify-between border-b border-gray-100 p-6">
            <h2 id={titleId} className="text-lg font-semibold text-gray-900">
              {title}
            </h2>
            <button
              onClick={onClose}
              className="rounded-lg p-1 text-gray-500 transition-colors hover:bg-gray-100"
              aria-label="Close dialog"
            >
              <FiX size={20} />
            </button>
          </div>
        )}
        <div className={hideHeader ? '' : 'p-6'}>{children}</div>
      </div>
    </div>
  );
}
