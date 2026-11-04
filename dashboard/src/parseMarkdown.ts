export interface ListItem {
  text: string;
  children: string[];
}

export type Block =
  | { kind: "heading"; level: 1 | 2; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; start: number; items: ListItem[] };

export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  for (const line of source.split("\n")) {
    if (!line.trim()) continue;
    const heading = /^(#{1,2}) (.*)$/.exec(line);
    const numbered = /^(\d+)\. (.*)$/.exec(line);
    const bullet = /^(\s*)- (.*)$/.exec(line);
    const last = blocks.at(-1);
    if (heading) {
      const level = heading[1] === "#" ? 1 : 2;
      blocks.push({ kind: "heading", level, text: heading[2] });
    } else if (numbered) {
      addItem(blocks, last, true, numbered[2], Number(numbered[1]));
    } else if (bullet?.[1] && last?.kind === "list") {
      last.items.at(-1)?.children.push(bullet[2]);
    } else if (bullet) {
      addItem(blocks, last, false, bullet[2], 1);
    } else {
      blocks.push({ kind: "paragraph", text: line.trim() });
    }
  }
  return blocks;
}

function addItem(
  blocks: Block[],
  last: Block | undefined,
  ordered: boolean,
  text: string,
  number: number,
): void {
  const item = { text, children: [] };
  if (last?.kind === "list" && last.ordered === ordered) {
    last.items.push(item);
  } else {
    blocks.push({ kind: "list", ordered, start: number, items: [item] });
  }
}
