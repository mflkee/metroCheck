import { type MouseEvent, type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

type ModalProps = {
  title: string;
  description?: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "default" | "sm" | "xl";
};

export function Modal({
  title,
  description,
  open,
  onClose,
  children,
  footer,
  size = "default",
}: ModalProps) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  if (typeof document === "undefined") {
    return null;
  }

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }

  return createPortal(
    <div
      aria-modal="true"
      className="fixed inset-0 z-[260] flex items-end justify-center overflow-y-auto overscroll-contain bg-[rgba(11,20,27,0.42)] px-2 py-2 sm:items-center sm:px-4 sm:py-8"
      role="dialog"
      onClick={handleBackdropClick}
    >
      <div
        className={[
          "tone-parent flex w-full flex-col overflow-hidden rounded-[24px] border border-line shadow-panel sm:my-auto sm:rounded-[28px]",
          size === "sm"
            ? "max-h-[calc(100dvh-1rem)] sm:max-h-[calc(100vh-4rem)] sm:max-w-md"
            : size === "xl"
              ? "max-h-[calc(100dvh-1rem)] sm:max-h-[calc(100vh-1.5rem)] sm:max-w-[min(98vw,110rem)]"
              : "max-h-[calc(100dvh-1rem)] sm:max-h-[calc(100vh-4rem)] sm:max-w-2xl",
        ].join(" ")}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-4 sm:px-6 sm:py-5">
          <div className="min-w-0">
            <h3 className="text-xl font-semibold text-ink">{title}</h3>
            {description ? <p className="mt-1 text-sm text-steel">{description}</p> : null}
          </div>
          <button
            aria-label="Закрыть"
            className="icon-action-button icon-action-button--tiny"
            type="button"
            onClick={onClose}
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5">{children}</div>
        {footer ? <div className="border-t border-line px-4 py-4 sm:px-6">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
