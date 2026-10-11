import type { ButtonHTMLAttributes, ReactNode } from "react";

type IconActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  icon: ReactNode;
  size?: "default" | "tiny";
};

export function IconActionButton({
  className,
  icon,
  label,
  size = "default",
  title,
  type = "button",
  ...props
}: IconActionButtonProps) {
  return (
    <button
      aria-label={label}
      className={[
        "icon-action-button",
        size === "tiny" ? "icon-action-button--tiny" : "",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      title={title ?? label}
      type={type}
      {...props}
    >
      {icon}
    </button>
  );
}
