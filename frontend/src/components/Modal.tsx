import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  footer?: ReactNode;
  maxWidth?: string;
}

export function Modal({ open, onClose, title, children, footer, maxWidth = 'max-w-lg' }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`max-h-[90vh] w-full ${maxWidth} overflow-y-auto rounded-card border border-line bg-surface-2 p-6 shadow-modal focus:outline-none`}
      >
        {title && (
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-medium text-ink-primary">{title}</h3>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-ink-muted transition-colors hover:text-ink-primary"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        )}
        {children}
        {footer && <div className="mt-4">{footer}</div>}
      </div>
    </div>
  );
}
