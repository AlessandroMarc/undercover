import { expect, it } from "vitest";
import { parseMarkdown } from "./parseMarkdown";

it("parses headings, paragraphs and lists", () => {
  const blocks = parseMarkdown(
    [
      "# Title",
      "",
      "Some text.",
      "",
      "## Steps",
      "1. First",
      "2. Second",
      "   - Detail",
      "- Bullet",
    ].join("\n"),
  );
  expect(blocks).toEqual([
    { kind: "heading", level: 1, text: "Title" },
    { kind: "paragraph", text: "Some text." },
    { kind: "heading", level: 2, text: "Steps" },
    {
      kind: "list",
      ordered: true,
      start: 1,
      items: [
        { text: "First", children: [] },
        { text: "Second", children: ["Detail"] },
      ],
    },
    {
      kind: "list",
      ordered: false,
      start: 1,
      items: [{ text: "Bullet", children: [] }],
    },
  ]);
});

it("keeps the numbers of a list that a paragraph interrupts", () => {
  const blocks = parseMarkdown("1. One\n\nA note.\n\n2. Two");
  expect(blocks.map((block) => block.kind)).toEqual([
    "list",
    "paragraph",
    "list",
  ]);
  expect(blocks[2]).toMatchObject({ start: 2 });
});
