import { useEffect, useId, useMemo, useRef, useState } from "react";

import { FloatingAutocompleteMenu } from "@/components/floating-autocomplete-menu";

export type SearchableOption<T extends string | number = number> = {
  value: T;
  label: string;
  hint?: string;
};

type SharedProps<T extends string | number> = {
  options: SearchableOption<T>[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
  /** Caps the rendered results, e.g. 5 for an equipment picker. */
  maxResults?: number;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
};

type SingleProps<T extends string | number> = SharedProps<T> & {
  value: T | null;
  onChange: (next: T | null) => void;
};

type MultiProps<T extends string | number> = SharedProps<T> & {
  value: T[];
  onChange: (next: T[]) => void;
  /** Recent queries shown when the search box is empty. */
  history?: string[];
  /** Called when a query is actually used (a selection or Enter), to record it. */
  onQueryCommitted?: (query: string) => void;
  /** Mirrors the typed query, for callers that search on the server. */
  onQueryChange?: (query: string) => void;
  /** Turn off when the caller already filtered the options (e.g. a server-side search). */
  filterLocally?: boolean;
};

/**
 * Closes the menu on an outside pointer press. The menu is portalled to the body, so containment
 * has to be checked against both the field and the menu.
 */
function useOutsideClose(onClose: () => void) {
  const fieldRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (fieldRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      onClose();
    }
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, [onClose]);
  return { fieldRef, menuRef };
}

/** Case-, ё- and spacing-insensitive form used to compare a query with an option. */
function normalizeForSearch(value: string): string {
  return value.toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
}

/**
 * Every word of the query has to appear somewhere in the option, in any order, so "влажности
 * анализатор" and "анализатор влажности" both find "Анализатор Влажности".
 */
function matchesSearch(haystack: string, query: string): boolean {
  const words = normalizeForSearch(query).split(" ").filter(Boolean);
  if (!words.length) {
    return true;
  }
  const normalized = normalizeForSearch(haystack);
  return words.every((word) => normalized.includes(word));
}

function useFiltered<T extends string | number>(
  options: SearchableOption<T>[],
  query: string,
  maxResults?: number,
  filterLocally = true,
) {
  return useMemo(() => {
    const matches = filterLocally
      ? options.filter((option) => matchesSearch(`${option.label} ${option.hint ?? ""}`, query))
      : options;
    return typeof maxResults === "number" ? matches.slice(0, maxResults) : matches;
  }, [filterLocally, maxResults, options, query]);
}

function useHighlightScroll(
  open: boolean,
  highlighted: number,
  optionRefs: React.RefObject<Array<HTMLButtonElement | null>>,
) {
  useEffect(() => {
    if (!open) {
      return;
    }
    // jsdom (tests) has no scrollIntoView, hence the optional call.
    optionRefs.current?.[highlighted]?.scrollIntoView?.({ block: "nearest" });
  }, [highlighted, open, optionRefs]);
}

function optionClassName(highlighted: boolean): string {
  return [
    "block w-full rounded-lg px-2 py-1.5 text-left text-sm text-ink transition",
    highlighted ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--accent-soft)]",
  ].join(" ");
}

/**
 * Searchable single choice. The input doubles as the search box: on focus it clears to show the
 * whole list, and when closed it shows the current label. Keyboard: arrows, Enter, Escape.
 * The list is rendered outside the layout (portal + fixed), so a modal never clips it.
 */
export function SearchableSelect<T extends string | number>({
  options,
  value,
  onChange,
  placeholder = "— выберите —",
  searchPlaceholder = "Поиск…",
  emptyLabel = "Ничего не найдено",
  maxResults,
  loading = false,
  disabled = false,
  className,
}: SingleProps<T>) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const { fieldRef, menuRef } = useOutsideClose(() => setOpen(false));
  const listboxId = useId();
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const filtered = useFiltered(options, query, maxResults);
  const selected = options.find((option) => option.value === value) ?? null;
  useHighlightScroll(open, highlighted, optionRefs);

  useEffect(() => {
    setHighlighted(0);
  }, [query, open]);

  function choose(option: SearchableOption<T>) {
    onChange(option.value);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className={["relative", className].filter(Boolean).join(" ")} ref={fieldRef}>
      <input
        aria-controls={open ? listboxId : undefined}
        aria-expanded={open}
        aria-haspopup="listbox"
        autoComplete="off"
        className="form-input"
        disabled={disabled}
        placeholder={open ? searchPlaceholder : placeholder}
        role="combobox"
        value={open ? query : (selected?.label ?? "")}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setHighlighted((current) => Math.min(current + 1, filtered.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setHighlighted((current) => Math.max(current - 1, 0));
          } else if (event.key === "Enter" && open && filtered[highlighted]) {
            event.preventDefault();
            choose(filtered[highlighted]);
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      <FloatingAutocompleteMenu
        anchorRef={fieldRef}
        id={listboxId}
        layoutKey={`${query}\u0000${filtered.map((option) => option.value).join(",")}`}
        menuRef={menuRef}
        open={open}
      >
        {loading ? <p className="px-2 py-1.5 text-sm text-steel">Загрузка…</p> : null}
        {!loading && filtered.length === 0 ? (
          <p className="px-2 py-1.5 text-sm text-steel">{emptyLabel}</p>
        ) : null}
        {filtered.map((option, index) => (
          <button
            key={option.value}
            ref={(node) => {
              optionRefs.current[index] = node;
            }}
            aria-selected={option.value === value}
            className={optionClassName(index === highlighted)}
            role="option"
            type="button"
            onMouseEnter={() => setHighlighted(index)}
            onClick={() => choose(option)}
          >
            <span className="block truncate">{option.label}</span>
            {option.hint ? (
              <span className="block truncate text-xs text-steel">{option.hint}</span>
            ) : null}
          </button>
        ))}
      </FloatingAutocompleteMenu>
    </div>
  );
}

/**
 * Searchable multiple choice with removable chips. Same visual language and the same portalled
 * menu as the single variant; the results are capped by `maxResults` (the equipment picker uses 5).
 */
export function SearchableMultiSelect<T extends string | number>({
  options,
  value,
  onChange,
  placeholder = "Начните вводить…",
  emptyLabel = "Ничего не найдено",
  maxResults,
  loading = false,
  disabled = false,
  className,
  history,
  onQueryCommitted,
  onQueryChange,
  filterLocally = true,
}: MultiProps<T>) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const { fieldRef, menuRef } = useOutsideClose(() => setOpen(false));
  const listboxId = useId();
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const filtered = useFiltered(
    options.filter((option) => !value.includes(option.value)),
    query,
    maxResults,
    filterLocally,
  );
  useHighlightScroll(open, highlighted, optionRefs);
  const selected = value
    .map((id) => options.find((option) => option.value === id))
    .filter((option): option is SearchableOption<T> => Boolean(option));

  useEffect(() => {
    setHighlighted(0);
  }, [query, open]);

  function add(option: SearchableOption<T>) {
    onChange([...value, option.value]);
    if (query.trim()) {
      onQueryCommitted?.(query);
    }
    setQuery("");
    onQueryChange?.("");
  }

  function updateQuery(next: string) {
    setQuery(next);
    onQueryChange?.(next);
  }

  const showHistory = query.trim() === "" && (history?.length ?? 0) > 0;

  return (
    <div className={["relative", className].filter(Boolean).join(" ")} ref={fieldRef}>
      <input
        aria-controls={open ? listboxId : undefined}
        aria-expanded={open}
        aria-haspopup="listbox"
        autoComplete="off"
        className="form-input"
        disabled={disabled}
        placeholder={placeholder}
        role="combobox"
        value={query}
        onChange={(event) => {
          updateQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setHighlighted((current) => Math.min(current + 1, filtered.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setHighlighted((current) => Math.max(current - 1, 0));
          } else if (event.key === "Enter" && open && filtered[highlighted]) {
            event.preventDefault();
            add(filtered[highlighted]);
            setOpen(true);
          } else if (event.key === "Enter" && query.trim()) {
            onQueryCommitted?.(query);
          } else if (event.key === "Escape") {
            setOpen(false);
          } else if (event.key === "Backspace" && query === "" && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
      />
      {/* The picked items sit under the field, so the field itself never moves down as they pile up. */}
      {selected.length ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {selected.map((option) => (
            <span
              key={option.value}
              className="inline-flex max-w-full items-center gap-1 rounded-full border border-line px-2 py-0.5 text-xs text-ink"
            >
              <span className="truncate">{option.label}</span>
              <button
                aria-label={`Убрать ${option.label}`}
                className="text-steel transition hover:text-[color:var(--danger-text)]"
                disabled={disabled}
                type="button"
                onClick={() => onChange(value.filter((entry) => entry !== option.value))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <FloatingAutocompleteMenu
        anchorRef={fieldRef}
        id={listboxId}
        layoutKey={`${query}\u0000${showHistory ? (history ?? []).join(",") : ""}\u0000${filtered
          .map((option) => option.value)
          .join(",")}`}
        menuRef={menuRef}
        open={open}
      >
        {showHistory ? (
          <div className="mb-1 border-b border-line pb-1">
            <p className="px-2 pt-1 text-[11px] font-semibold uppercase tracking-wide text-steel">
              Последние запросы
            </p>
            {history?.map((entry) => (
              <button
                key={entry}
                className="block w-full truncate rounded-lg px-2 py-1.5 text-left text-sm text-steel transition hover:bg-[var(--accent-soft)] hover:text-ink"
                role="option"
                type="button"
                aria-selected={false}
                onClick={() => updateQuery(entry)}
              >
                {entry}
              </button>
            ))}
          </div>
        ) : null}
        {loading ? <p className="px-2 py-1.5 text-sm text-steel">Загрузка…</p> : null}
        {!loading && filtered.length === 0 && !showHistory ? (
          <p className="px-2 py-1.5 text-sm text-steel">{emptyLabel}</p>
        ) : null}
        {filtered.map((option, index) => (
          <button
            key={option.value}
            ref={(node) => {
              optionRefs.current[index] = node;
            }}
            className={optionClassName(index === highlighted)}
            role="option"
            type="button"
            onMouseEnter={() => setHighlighted(index)}
            onClick={() => add(option)}
          >
            <span className="block truncate">{option.label}</span>
            {option.hint ? (
              <span className="block truncate text-xs text-steel">{option.hint}</span>
            ) : null}
          </button>
        ))}
      </FloatingAutocompleteMenu>
    </div>
  );
}
