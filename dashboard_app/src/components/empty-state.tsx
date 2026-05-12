import type { ReactNode } from "react";

export function EmptyState({
  body,
  icon,
  producerPath,
  title
}: {
  body: string;
  icon?: ReactNode;
  producerPath?: string;
  title: string;
}) {
  return (
    <section className="empty-state">
      {icon ? <div className="empty-state__icon" aria-hidden="true">{icon}</div> : null}
      <h2>{title}</h2>
      <p>{body}</p>
      {producerPath ? (
        <p className="empty-state__producer">
          Produced by: <code className="empty-state__producer-path">{producerPath}</code>
        </p>
      ) : null}
    </section>
  );
}
