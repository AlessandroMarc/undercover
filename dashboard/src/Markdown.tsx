import { Fragment, type ReactNode } from "react";
import { parseMarkdown } from "./parseMarkdown";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, index) => {
    if (part.startsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export function Markdown({ source }: Readonly<{ source: string }>) {
  return (
    <div className="prose">
      {parseMarkdown(source).map((block, index) => {
        if (block.kind === "heading") {
          const Heading = block.level === 1 ? "h2" : "h3";
          return <Heading key={index}>{inline(block.text)}</Heading>;
        }
        if (block.kind === "paragraph") {
          return <p key={index}>{inline(block.text)}</p>;
        }
        const List = block.ordered ? "ol" : "ul";
        return (
          <List key={index} start={block.ordered ? block.start : undefined}>
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex}>
                {inline(item.text)}
                {item.children.length > 0 && (
                  <ul>
                    {item.children.map((child, childIndex) => (
                      <li key={childIndex}>{inline(child)}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
