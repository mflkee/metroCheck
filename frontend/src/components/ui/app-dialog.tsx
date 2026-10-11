import { type ReactNode } from "react";

import { IconActionButton } from "@/components/icon-action-button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

type AppDialogProps = {
  title: string;
  description?: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  headerActions?: ReactNode;
  size?: "default" | "sm" | "xl";
};

const SIZE_CLASS: Record<NonNullable<AppDialogProps["size"]>, string> = {
  sm: "sm:max-h-[calc(100vh-4rem)] sm:max-w-md",
  default: "sm:max-h-[calc(100vh-4rem)] sm:max-w-2xl",
  xl: "sm:max-h-[calc(100vh-1.5rem)] sm:max-w-[min(98vw,110rem)]",
};

/**
 * Dialog adopted from the shared primitive (Radix, through the vendored `@/components/ui/dialog`)
 * while keeping metroLog's look and contract.
 *
 * Dismissal contract: it never closes on an outside (backdrop) click - only through the explicit
 * close control or the Escape key. Radix still adds what the hand-rolled modal lacked: a focus
 * trap, the aria wiring (`role="dialog"`, `aria-modal`, title/description) and a scroll lock.
 *
 * The wrapper owns the visual shell, so the `DialogContent` defaults are neutralised explicitly
 * (`bg-transparent border-0 p-0 gap-0 shadow-none rounded-none`) and the card is rendered inside.
 */
export function AppDialog({
  title,
  description,
  open,
  onClose,
  children,
  footer,
  headerActions,
  size = "default",
}: AppDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <DialogContent
        showCloseButton={false}
        onInteractOutside={(event) => event.preventDefault()}
        onPointerDownOutside={(event) => event.preventDefault()}
        className={[
          "fixed inset-0 z-[260] flex w-full max-w-none items-end justify-center px-2 py-2",
          "translate-x-0 translate-y-0 border-0 bg-transparent p-0 shadow-none sm:max-w-none sm:items-center sm:px-4 sm:py-8",
          "gap-0 rounded-none",
        ].join(" ")}
      >
        <div
          className={[
            "tone-parent flex w-full flex-col overflow-hidden border border-line shadow-panel",
            "max-h-[calc(100dvh-1rem)] rounded-[24px] sm:my-auto sm:rounded-[28px]",
            SIZE_CLASS[size],
          ].join(" ")}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-4 sm:px-6 sm:py-5">
            <div className="min-w-0">
              <DialogTitle className="text-xl font-semibold text-ink">{title}</DialogTitle>
              {description ? (
                <DialogDescription className="mt-1 text-sm text-steel">{description}</DialogDescription>
              ) : null}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {headerActions}
              <IconActionButton
                icon={
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                }
                label="Закрыть"
                onClick={onClose}
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5">{children}</div>
          {footer ? <div className="border-t border-line px-4 py-4 sm:px-6">{footer}</div> : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
