"use client";

export type ErrorStateVariant = "page" | "inline";

export function ErrorState({
  hint,
  message,
  retry,
  title,
  variant = "page"
}: {
  hint?: string;
  message: string;
  retry?: () => void;
  title: string;
  variant?: ErrorStateVariant;
}) {
  return (
    <div className={`error-state error-state--${variant}`}>
      <h2 className="error-state__title">{title}</h2>
      <p className="error-state__message">{message}</p>
      {hint ? <p className="error-state__hint">{hint}</p> : null}
      {retry ? (
        <button className="error-state__retry" onClick={retry} type="button">
          Try again
        </button>
      ) : null}
    </div>
  );
}
