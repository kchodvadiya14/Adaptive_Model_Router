import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export function MarkdownContent({ content, className = '' }: MarkdownContentProps) {
  return (
    <div className={`markdown-body text-sm leading-relaxed text-ink-primary ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="text-ink-primary">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-ink-primary">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          h1: ({ children }) => <h1 className="mb-2 mt-4 text-base font-semibold text-ink-primary first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-4 text-sm font-semibold text-ink-primary first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-3 text-sm font-semibold text-ink-primary first:mt-0">{children}</h3>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-brand-300 underline hover:text-brand-200">
              {children}
            </a>
          ),
          code: ({ className: codeClassName, children }) => {
            const isBlock = /language-/.test(codeClassName ?? '');
            if (isBlock) {
              return (
                <code className={`${codeClassName ?? ''} font-mono text-xs`}>
                  {children}
                </code>
              );
            }
            return (
              <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-xs text-brand-300">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="mb-3 overflow-x-auto rounded-lg border border-line bg-surface-3/60 px-3 py-2.5 last:mb-0">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="mb-3 border-l-2 border-line pl-3 text-ink-secondary last:mb-0">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="mb-3 overflow-x-auto rounded-lg border border-line last:mb-0">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-surface-3/60">{children}</thead>,
          tbody: ({ children }) => <tbody className="divide-y divide-line">{children}</tbody>,
          tr: ({ children }) => <tr className="divide-x divide-line">{children}</tr>,
          th: ({ children }) => (
            <th className="px-3 py-2 text-left font-medium text-ink-secondary">{children}</th>
          ),
          td: ({ children }) => <td className="px-3 py-2 align-top text-ink-primary">{children}</td>,
          hr: () => <hr className="my-3 border-line" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
