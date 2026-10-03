import type { ReactNode } from "react";

export type ChipVariant =
  | "default"
  | "status-accepted"
  | "status-superseded"
  | "status-proposed"
  | "status-reaffirmation"
  | "grade-a"
  | "grade-b"
  | "grade-c"
  | "grade-d"
  | "grade-f"
  | "neutral";

export function Chip({
  children,
  title,
  variant = "default"
}: {
  children: ReactNode;
  title?: string;
  variant?: ChipVariant;
}) {
  return (
    <span className={`chip chip--${variant}`} title={title}>
      {children}
    </span>
  );
}
