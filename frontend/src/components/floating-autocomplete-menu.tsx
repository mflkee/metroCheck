import { type ReactNode, type RefObject, useCallback, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

export type FloatingAutocompleteMenuPlacement = "bottom" | "top";

type FloatingAutocompleteMenuProps<TAnchor extends HTMLElement> = {
  anchorRef: RefObject<TAnchor | null>;
  children: ReactNode | ((placement: FloatingAutocompleteMenuPlacement) => ReactNode);
  id: string;
  layoutKey: string;
  menuRef: RefObject<HTMLDivElement | null>;
  open: boolean;
};

const MENU_GAP = 6;
const MENU_MAX_HEIGHT = 384;
const MENU_MIN_HEIGHT = 180;
const MENU_MIN_WIDTH = 180;
const VIEWPORT_PADDING = 16;

export function FloatingAutocompleteMenu<TAnchor extends HTMLElement>({
  anchorRef,
  children,
  id,
  layoutKey,
  menuRef,
  open,
}: FloatingAutocompleteMenuProps<TAnchor>) {
  const [position, setPosition] = useState<{
    left: number;
    maxHeight: number;
    placement: FloatingAutocompleteMenuPlacement;
    top: number;
    width: number;
  } | null>(null);

  const updatePosition = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor || typeof window === "undefined") {
      return;
    }

    const anchorRect = anchor.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const maxWidth = Math.max(MENU_MIN_WIDTH, viewportWidth - VIEWPORT_PADDING * 2);
    const width = Math.min(Math.max(anchorRect.width, MENU_MIN_WIDTH), maxWidth);
    const maxLeft = viewportWidth - VIEWPORT_PADDING - width;
    const left = Math.max(VIEWPORT_PADDING, Math.min(anchorRect.left, maxLeft));

    /*
     * The list always drops below its field. Flipping it above covered the very input you are
     * typing into, so instead it shrinks into the room below and, when even that is tight, slides
     * up just enough to stay inside the viewport.
     */
    const placement: FloatingAutocompleteMenuPlacement = "bottom";
    const spaceBelow = viewportHeight - anchorRect.bottom - VIEWPORT_PADDING - MENU_GAP;
    const maxHeight = Math.min(MENU_MAX_HEIGHT, Math.max(MENU_MIN_HEIGHT, spaceBelow));
    const desiredTop = anchorRect.bottom + MENU_GAP;
    const maxTop = Math.max(VIEWPORT_PADDING, viewportHeight - VIEWPORT_PADDING - maxHeight);
    const top = Math.max(VIEWPORT_PADDING, Math.min(desiredTop, maxTop));

    setPosition({ left, maxHeight, placement, top, width });
  }, [anchorRef, menuRef]);

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return undefined;
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [layoutKey, open, updatePosition]);

  const placement = position?.placement ?? "bottom";

  /*
   * A modal dialog installs a document-level, non-passive wheel listener
   * (`react-remove-scroll`) that cancels the wheel for everything outside the dialog, so a menu
   * rendered into `document.body` cannot scroll. Inside a dialog the menu is portalled into the
   * dialog element itself; outside one it keeps going to the body.
   */
  const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(null);

  useLayoutEffect(() => {
    if (!open) {
      setPortalContainer(null);
      return;
    }
    const dialog = anchorRef.current?.closest('[role="dialog"]');
    setPortalContainer(dialog instanceof HTMLElement ? dialog : document.body);
  }, [anchorRef, open]);

  useLayoutEffect(() => {
    if (!open || !menuRef.current) {
      return;
    }

    menuRef.current.scrollTop = placement === "top" ? menuRef.current.scrollHeight : 0;
  }, [layoutKey, menuRef, open, placement]);

  if (!open || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      className="autocomplete-input__menu"
      data-placement={placement}
      id={id}
      ref={menuRef}
      role="listbox"
      style={
        position
          ? {
              left: position.left,
              maxHeight: position.maxHeight,
              top: position.top,
              width: position.width,
            }
          : { visibility: "hidden" }
      }
    >
      {typeof children === "function" ? children(placement) : children}
    </div>,
    portalContainer ?? document.body,
  );
}
