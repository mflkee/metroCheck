import { type ChangeEvent, type InputHTMLAttributes } from "react";

import { sanitizeNumericInput } from "@/lib/numericInput";

type NumberInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "autoComplete" | "inputMode" | "onChange" | "type" | "value"
> & {
  value: string;
  onValueChange: (value: string) => void;
  /** Keep one decimal separator (`,` is normalised to `.`). Integers by default. */
  allowDecimal?: boolean;
  /** Keep a leading minus. Positive values only by default. */
  allowNegative?: boolean;
};

/**
 * A numeric field the app owns, mirroring `DateInput` and `Select`: the browser is handed a text
 * field, so it never changes the value on a wheel scroll, never raises its own validation bubble
 * and never accepts `e`, `+` or a locale separator. Only digits reach the caller.
 */
export function NumberInput({
  value,
  onValueChange,
  allowDecimal = false,
  allowNegative = false,
  maxLength,
  ...rest
}: NumberInputProps) {
  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    onValueChange(
      sanitizeNumericInput(event.target.value, { allowDecimal, allowNegative, maxLength }),
    );
  }

  return (
    <input
      {...rest}
      autoComplete="off"
      inputMode={allowDecimal ? "decimal" : "numeric"}
      maxLength={maxLength}
      type="text"
      value={value}
      onChange={handleChange}
    />
  );
}
