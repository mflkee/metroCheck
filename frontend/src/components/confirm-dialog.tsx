import { useState, type ReactNode } from "react"
import { AppDialog } from "@/components/ui/app-dialog"

/**
 * The confirmation the app asks before something irreversible.
 *
 * It is the fleet dialog (from `@metro/app-dialog`) behind the call-site API the pages
 * already use: the trigger is rendered as-is and opens the dialog, and the refusal is
 * asked in the app's own window rather than the browser's.
 */
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel = "Подтвердить",
  destructive = false,
  onConfirm,
}: {
  trigger: ReactNode
  title: string
  description?: string
  confirmLabel?: string
  destructive?: boolean
  onConfirm: () => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <>
      {/* `contents` keeps the layout untouched while the click bubbles from the button. */}
      <span className="contents" onClick={() => setOpen(true)}>
        {trigger}
      </span>
      <AppDialog
        description={description}
        footer={
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" type="button" onClick={() => setOpen(false)}>
              Отмена
            </button>
            <button
              className={destructive ? "btn-danger" : "btn-primary"}
              type="button"
              onClick={() => {
                setOpen(false)
                onConfirm()
              }}
            >
              {confirmLabel}
            </button>
          </div>
        }
        open={open}
        size="sm"
        title={title}
        onClose={() => setOpen(false)}
      >
        {/* The question is the title and the consequence is the description, so the body is empty. */}
        {null}
      </AppDialog>
    </>
  )
}
