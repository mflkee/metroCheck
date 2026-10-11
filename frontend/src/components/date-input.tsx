import {
  type ComponentPropsWithoutRef,
  type FocusEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  forwardRef,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import { ru } from "date-fns/locale";
import { DayPicker } from "react-day-picker";

type DateInputProps = Omit<ComponentPropsWithoutRef<"input">, "type" | "value" | "onChange"> & {
  value: string | null | undefined;
  onChange: (value: string) => void;
  onEnter?: () => void;
};

const DATE_PICKER_MIN_WIDTH = 272;
const DATE_PICKER_GAP = 8;
const VIEWPORT_PADDING = 16;

export const DateInput = forwardRef<HTMLInputElement, DateInputProps>(function DateInput(
  {
    className,
    onBlur,
    onChange,
    onEnter,
    onKeyDown,
    placeholder,
    style,
    value,
    ...props
  },
  ref,
) {
  const isCompact = className?.includes("form-input--compact") ?? false;
  const [displayText, setDisplayText] = useState(() => formatIsoDateForDisplay(value));
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState<Date>(() => parseIsoDateToDate(value) ?? new Date());
  const [popoverPosition, setPopoverPosition] = useState<{ top: number; left: number } | null>(
    null,
  );

  const containerRef = useRef<HTMLDivElement | null>(null);
  const fieldWrapRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const interactingInsideRef = useRef(false);

  const selectedIsoDate = useMemo(
    () => parseDateInput(displayText) ?? value ?? null,
    [displayText, value],
  );
  const selectedDate = useMemo(() => parseIsoDateToDate(selectedIsoDate), [selectedIsoDate]);

  useEffect(() => {
    setDisplayText(formatIsoDateForDisplay(value));
  }, [value]);

  useEffect(() => {
    if (!calendarOpen) {
      return;
    }
    setCalendarMonth(selectedDate ?? new Date());
  }, [calendarOpen, selectedDate]);

  useEffect(() => {
    if (!calendarOpen) {
      setPopoverPosition(null);
      return undefined;
    }

    function handlePointerDown(event: MouseEvent) {
      const targetNode = event.target as Node;
      if (
        containerRef.current?.contains(targetNode)
        || popoverRef.current?.contains(targetNode)
      ) {
        return;
      }
      setCalendarOpen(false);
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }
      setCalendarOpen(false);
      inputRef.current?.focus();
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    function updatePopoverPosition() {
      const anchor = fieldWrapRef.current;
      if (!anchor || typeof window === "undefined") {
        return;
      }

      const anchorRect = anchor.getBoundingClientRect();
      const popoverWidth = Math.max(popoverRef.current?.offsetWidth ?? 0, DATE_PICKER_MIN_WIDTH);
      const preferredLeft = anchorRect.right - popoverWidth;
      const maxLeft = window.innerWidth - VIEWPORT_PADDING - popoverWidth;
      const left = Math.max(VIEWPORT_PADDING, Math.min(preferredLeft, maxLeft));

      const popoverHeight = popoverRef.current?.offsetHeight ?? 0;
      const spaceBelow = window.innerHeight - anchorRect.bottom - VIEWPORT_PADDING;
      const spaceAbove = anchorRect.top - VIEWPORT_PADDING;
      const shouldOpenAbove = popoverHeight > 0 && spaceBelow < popoverHeight && spaceAbove > spaceBelow;
      const fallbackTop = anchorRect.bottom + DATE_PICKER_GAP;
      const preferredTop = shouldOpenAbove
        ? anchorRect.top - popoverHeight - DATE_PICKER_GAP
        : fallbackTop;
      const maxTop = Math.max(VIEWPORT_PADDING, window.innerHeight - VIEWPORT_PADDING - popoverHeight);
      const top = Math.max(VIEWPORT_PADDING, Math.min(preferredTop, maxTop));

      setPopoverPosition({ top, left });
    }

    updatePopoverPosition();
    window.addEventListener("resize", updatePopoverPosition);
    window.addEventListener("scroll", updatePopoverPosition, true);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
      window.removeEventListener("resize", updatePopoverPosition);
      window.removeEventListener("scroll", updatePopoverPosition, true);
    };
  }, [calendarOpen]);

  function assignInputRef(node: HTMLInputElement | null) {
    inputRef.current = node;
    if (typeof ref === "function") {
      ref(node);
      return;
    }
    if (ref) {
      ref.current = node;
    }
  }

  function markInteractingInside() {
    interactingInsideRef.current = true;
    window.setTimeout(() => {
      interactingInsideRef.current = false;
    }, 0);
  }

  function syncText(nextText: string) {
    setDisplayText(nextText);

    const parsedIsoDate = parseDateInput(nextText);
    if (parsedIsoDate) {
      onChange(parsedIsoDate);
      return parsedIsoDate;
    }

    if (!hasDateDigits(nextText)) {
      onChange("");
      return "";
    }

    return null;
  }

  function commitText(): string | null {
    const parsedIsoDate = parseDateInput(displayText);
    if (parsedIsoDate) {
      setDisplayText(formatIsoDateForDisplay(parsedIsoDate));
      onChange(parsedIsoDate);
      return parsedIsoDate;
    }

    if (!hasDateDigits(displayText)) {
      setDisplayText("");
      onChange("");
      return "";
    }

    setDisplayText(formatIsoDateForDisplay(value));
    return null;
  }

  function handleBlur(event: FocusEvent<HTMLInputElement>) {
    const nextFocusedNode = event.relatedTarget;
    if (
      (nextFocusedNode && containerRef.current?.contains(nextFocusedNode))
      || (nextFocusedNode && popoverRef.current?.contains(nextFocusedNode))
      || interactingInsideRef.current
    ) {
      onBlur?.(event);
      return;
    }

    commitText();
    setCalendarOpen(false);
    onBlur?.(event);
  }

  function handleCalendarSelect(date: Date | undefined) {
    if (!date) {
      return;
    }
    const isoDate = formatDateObjectToIso(date);
    setDisplayText(formatIsoDateForDisplay(isoDate));
    onChange(isoDate);
    setCalendarMonth(date);
    setCalendarOpen(false);
    inputRef.current?.focus();
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();

      const committed = commitText();
      if (committed !== null || !hasDateDigits(displayText)) {
        if (onEnter) {
          onEnter();
        } else {
          event.currentTarget.form?.requestSubmit();
        }
      }
      return;
    }

    if (event.key === "ArrowDown" && (event.altKey || event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      setCalendarOpen(true);
      return;
    }

    if (event.key === "Escape" && calendarOpen) {
      event.preventDefault();
      setCalendarOpen(false);
      return;
    }

    onKeyDown?.(event);
  }

  return (
    <div className={["date-input", isCompact ? "date-input--compact" : ""].filter(Boolean).join(" ")} ref={containerRef}>
      <div className="date-input__field-wrap" ref={fieldWrapRef}>
        <input
          {...props}
          autoComplete="off"
          className={["date-input__field", className].filter(Boolean).join(" ")}
          inputMode="numeric"
          maxLength={props.maxLength ?? 10}
          placeholder={placeholder ?? "дд.мм.гггг"}
          ref={assignInputRef}
          style={style}
          type="text"
          value={displayText}
          onBlur={handleBlur}
          onChange={(event) => syncText(formatDateTypingValue(event.target.value))}
          onKeyDown={handleKeyDown}
        />

        <button
          aria-expanded={calendarOpen}
          aria-label="Открыть календарь"
          className="date-input__calendar-toggle"
          disabled={props.disabled || props.readOnly}
          onMouseDownCapture={markInteractingInside}
          onClick={() => setCalendarOpen((current) => !current)}
          type="button"
        >
          <svg
            aria-hidden="true"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="1.8"
          >
            <rect x="3.75" y="5.75" width="16.5" height="14.5" rx="2.25" />
            <path strokeLinecap="round" d="M7.5 3.75v4M16.5 3.75v4M3.75 9.5h16.5" />
          </svg>
        </button>

        {calendarOpen && typeof document !== "undefined"
          ? createPortal(
              <div
                className="date-input__popover"
                ref={popoverRef}
                style={
                  popoverPosition
                    ? {
                        left: popoverPosition.left,
                        top: popoverPosition.top,
                      }
                    : undefined
                }
                onMouseDownCapture={markInteractingInside}
              >
                <DayPicker
                  className="date-picker"
                  classNames={{
                    root: "date-picker__root",
                    months: "date-picker__months",
                    month: "date-picker__month",
                    month_caption: "date-picker__caption",
                    caption_label: "date-picker__caption-label",
                    nav: "date-picker__nav",
                    button_previous: "date-picker__nav-button",
                    button_next: "date-picker__nav-button",
                    chevron: "date-picker__chevron",
                    month_grid: "date-picker__grid",
                    weekdays: "date-picker__weekdays",
                    weekday: "date-picker__weekday",
                    day: "date-picker__day",
                    day_button: "date-picker__day-button",
                    today: "date-picker__day--today",
                    selected: "date-picker__day--selected",
                    outside: "date-picker__day--outside",
                    disabled: "date-picker__day--disabled",
                  }}
                  locale={ru}
                  mode="single"
                  month={calendarMonth}
                  selected={selectedDate ?? undefined}
                  showOutsideDays
                  onMonthChange={setCalendarMonth}
                  onSelect={handleCalendarSelect}
                />
              </div>,
              document.body,
            )
          : null}
      </div>
    </div>
  );
});

function formatDateTypingValue(rawValue: string): string {
  const normalizedValue = rawValue.replace(/[^\d.\-/ ]/g, "");
  if (/[.\-/ ]/.test(normalizedValue)) {
    return formatSeparatedDateTypingValue(normalizedValue);
  }
  return formatDateDigits(normalizedValue);
}

function formatDateDigits(rawValue: string): string {
  const digits = rawValue.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) {
    return digits;
  }
  if (digits.length <= 4) {
    return `${digits.slice(0, 2)}.${digits.slice(2)}`;
  }
  return `${digits.slice(0, 2)}.${digits.slice(2, 4)}.${digits.slice(4)}`;
}

function formatSeparatedDateTypingValue(rawValue: string): string {
  const hasTrailingSeparator = /[.\-/ ]$/.test(rawValue);
  const groups = rawValue.split(/[.\-/ ]/).map((group) => group.replace(/\D/g, ""));
  const day = (groups[0] ?? "").slice(0, 2);
  const monthSource = groups[1] ?? "";
  const month = monthSource.slice(0, 2);
  const year = `${monthSource.slice(2)}${groups.slice(2).join("")}`.slice(0, 4);
  const result: string[] = [];

  if (day || groups.length > 1 || hasTrailingSeparator) {
    result.push(day);
  }
  if (groups.length > 1 || hasTrailingSeparator) {
    result.push(month);
  }
  if (year || groups.length > 2 || (hasTrailingSeparator && month)) {
    result.push(year);
  }

  return result.join(".");
}

function hasDateDigits(value: string): boolean {
  return /\d/.test(value);
}

function parseDateInput(rawValue: string): string | null {
  const trimmedValue = rawValue.trim();
  if (!trimmedValue) {
    return null;
  }

  const parsedIsoDate = parseIsoDate(trimmedValue);
  if (parsedIsoDate) {
    return parsedIsoDate;
  }

  const displayMatch = trimmedValue.match(/^(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{4})$/);
  if (displayMatch) {
    return buildIsoDate(displayMatch[3], displayMatch[2], displayMatch[1]);
  }

  const digits = trimmedValue.replace(/\D/g, "");
  if (digits.length !== 8) {
    return null;
  }

  return buildIsoDate(digits.slice(4, 8), digits.slice(2, 4), digits.slice(0, 2));
}

function parseIsoDate(value: string): string | null {
  const isoMatch = value.match(/^(\d{4})[.\-/ ](\d{1,2})[.\-/ ](\d{1,2})$/);
  if (!isoMatch) {
    return null;
  }

  return buildIsoDate(isoMatch[1], isoMatch[2], isoMatch[3]);
}

function buildIsoDate(year: string, month: string, day: string): string | null {
  const numericYear = Number(year);
  const numericMonth = Number(month);
  const numericDay = Number(day);

  if (!isValidDateParts(numericYear, numericMonth, numericDay)) {
    return null;
  }

  return [
    String(numericYear).padStart(4, "0"),
    String(numericMonth).padStart(2, "0"),
    String(numericDay).padStart(2, "0"),
  ].join("-");
}

function isValidDateParts(year: number, month: number, day: number): boolean {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return false;
  }
  if (year < 1000 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31) {
    return false;
  }

  const candidate = new Date(Date.UTC(year, month - 1, day));
  return (
    candidate.getUTCFullYear() === year
    && candidate.getUTCMonth() === month - 1
    && candidate.getUTCDate() === day
  );
}

function formatIsoDateForDisplay(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  const isoMatch = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!isoMatch) {
    return value;
  }

  return `${isoMatch[3]}.${isoMatch[2]}.${isoMatch[1]}`;
}

function parseIsoDateToDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }

  const isoMatch = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!isoMatch) {
    return null;
  }

  const year = Number(isoMatch[1]);
  const monthIndex = Number(isoMatch[2]) - 1;
  const day = Number(isoMatch[3]);
  const candidate = new Date(year, monthIndex, day);

  if (
    candidate.getFullYear() !== year
    || candidate.getMonth() !== monthIndex
    || candidate.getDate() !== day
  ) {
    return null;
  }

  return candidate;
}

function formatDateObjectToIso(value: Date): string {
  return [
    String(value.getFullYear()).padStart(4, "0"),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}
