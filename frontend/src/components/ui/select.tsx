import { useEffect, useId, useRef, useState } from "react";

import { FloatingAutocompleteMenu } from "@/components/floating-autocomplete-menu";

export type SelectOption<T extends string | number = string> = {
  value: T;
  label: string;
  disabled?: boolean;
};

type SelectProps<T extends string | number> = {
  value: T;
  options: SelectOption<T>[];
  onChange: (next: T) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
  ariaLabel?: string;
  /** The dense variant used inside toolbars and inline editors (the old `form-input--compact`). */
  compact?: boolean;
};

function optionClassName(highlighted: boolean): string {
  return [
    "block w-full rounded-lg px-2 py-1.5 text-left text-sm text-ink transition",
    highlighted ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--accent-soft)]",
  ].join(" ");
}

/**
 * A single choice list drawn by the app itself.
 *
 * A native `<select>` opens an OS-drawn popup (a GTK menu on Linux), which looks nothing like the
 * rest of the interface, so every choice list goes through this component: the trigger looks like
 * `form-input`, and the list is the shared floating menu — portalled out of the layout (and into a
 * modal when there is one), so nothing clips it.
 *
 * Keyboard: arrows move, Enter/Space choose, Escape closes, Home/End jump.
 */
export function Select<T extends string | number>({
  value,
  options,
  onChange,
  placeholder = "— выберите —",
  disabled = false,
  className,
  id,
  ariaLabel,
  compact = false,
}: SelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const listboxId = useId();

  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null;

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    }
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    if (open) {
      setHighlighted(selectedIndex >= 0 ? selectedIndex : 0);
    }
  }, [open, selectedIndex]);

  useEffect(() => {
    if (open) {
      // jsdom (tests) has no scrollIntoView, hence the optional call.
      optionRefs.current?.[highlighted]?.scrollIntoView?.({ block: "nearest" });
    }
  }, [highlighted, open]);

  function choose(option: SelectOption<T>) {
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function moveHighlight(delta: number) {
    if (!options.length) {
      return;
    }
    let next = highlighted;
    for (let step = 0; step < options.length; step += 1) {
      next = (next + delta + options.length) % options.length;
      if (!options[next]?.disabled) {
        break;
      }
    }
    setHighlighted(next);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      moveHighlight(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const option = options[highlighted];
      if (option && !option.disabled) {
        choose(option);
      }
      return;
    }
    if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
      }
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      if (!open || !options.length) {
        return;
      }
      event.preventDefault();
      setHighlighted(event.key === "Home" ? 0 : options.length - 1);
    }
  }

  return (
    <div className={["relative", className].filter(Boolean).join(" ")}>
      <button
        ref={triggerRef}
        aria-controls={open ? listboxId : undefined}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
        className={["select-trigger", compact ? "select-trigger--compact" : ""].join(" ")}
        disabled={disabled}
        id={id}
        role="combobox"
        type="button"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={handleKeyDown}
      >
        <span className={["min-w-0 truncate", selected ? "" : "text-steel"].join(" ")}>
          {selected?.label ?? placeholder}
        </span>
        <svg
          aria-hidden="true"
          className={["h-4 w-4 shrink-0 text-steel transition-transform", open ? "rotate-180" : ""].join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <FloatingAutocompleteMenu
        anchorRef={triggerRef}
        id={listboxId}
        layoutKey={`${open}\u0000${options.map((option) => option.value).join(",")}`}
        menuRef={menuRef}
        open={open}
      >
        {options.map((option, index) => (
          <button
            key={option.value}
            ref={(node) => {
              optionRefs.current[index] = node;
            }}
            aria-selected={option.value === value}
            className={optionClassName(index === highlighted)}
            disabled={option.disabled}
            role="option"
            type="button"
            onMouseEnter={() => setHighlighted(index)}
            onClick={() => choose(option)}
          >
            <span className="block truncate">{option.label}</span>
          </button>
        ))}
      </FloatingAutocompleteMenu>
    </div>
  );
}
