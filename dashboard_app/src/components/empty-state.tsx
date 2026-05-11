export function EmptyState({
  body,
  title
}: {
  body: string;
  title: string;
}) {
  return (
    <section className="empty-state">
      <h2>{title}</h2>
      <p>{body}</p>
    </section>
  );
}
