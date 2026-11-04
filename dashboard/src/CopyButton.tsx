import { useState } from "react";

export function CopyButton({ text }: Readonly<{ text: string }>) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
    });
  };
  return (
    <button type="button" className="button quiet" onClick={copy}>
      {copied ? "Copied" : "Copy ID"}
    </button>
  );
}
