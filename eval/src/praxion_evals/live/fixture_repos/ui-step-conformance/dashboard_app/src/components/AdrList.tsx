export function AdrList({ adrs }: { adrs: { id: string; title: string }[] }) {
  return <ul>{adrs.map((a) => <li key={a.id}>{a.title}</li>)}</ul>;
}
