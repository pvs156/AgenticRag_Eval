import type { ReactNode } from "react";

// Renders the small Markdown subset the assistant emits (**bold**, _italic_, "- " lists, [12 CFR ...] cites)
// as React elements. Model output is never injected as HTML.

const INLINE = /(\*\*[^*]+\*\*|_[^_]+_|\[12 CFR [^\]]+\])/g;

export function inline(text: string, keyPrefix = ""): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const key = `${keyPrefix}${i}`;
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (/^_[^_]+_$/.test(part)) return <em key={key}>{part.slice(1, -1)}</em>;
    if (/^\[12 CFR [^\]]+\]$/.test(part))
      return (
        <span key={key} className="cite">
          {part.slice(1, -1)}
        </span>
      );
    return part;
  });
}

export function RichText({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, b) => {
        const lines = block.split("\n");
        const items = lines.filter((l) => l.startsWith("- "));
        const intro = lines.filter((l) => !l.startsWith("- "));
        return (
          <div key={b} className="mb-3 last:mb-0">
            {intro.map((l, i) => (
              <p key={i}>{inline(l, `${b}-${i}-`)}</p>
            ))}
            {items.length > 0 && (
              <ul className="ml-5 list-disc space-y-1">
                {items.map((l, i) => (
                  <li key={i}>{inline(l.slice(2), `${b}-li${i}-`)}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </>
  );
}
