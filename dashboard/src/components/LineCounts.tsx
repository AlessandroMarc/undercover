// How many lines a change added and removed, such as +12 −3.
export function LineCounts({
  added,
  removed,
}: Readonly<{ added: number; removed: number }>) {
  return (
    <span className="mono nowrap">
      <span className="diff-added-count">+{added}</span>{" "}
      <span className="diff-removed-count">−{removed}</span>
    </span>
  );
}
