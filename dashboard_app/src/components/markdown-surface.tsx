import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownSurface({ body }: { body: string }) {
  return (
    <div className="markdown-surface">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
    </div>
  );
}
