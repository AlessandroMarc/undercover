import { badgeFor, type IconName, type Tone } from "./status";
import type { DecisionKind, Status } from "./types";

const PATHS: Record<IconName, string> = {
  check: "M3 8.5l3.2 3.2L13 4.8",
  clock: "M8 4.5V8l2.5 1.5M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13z",
  question: "M6 6.2a2 2 0 113 1.7c-.7.5-1 .9-1 1.6M8 12v.5",
  dot: "M8 5.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5z",
  flag: "M4 14V2.5M4 3h8l-2 3 2 3H4",
  pen: "M3 13l1-3.5L10.8 2.7a1.4 1.4 0 012 2L6 11.5 3 13z",
};

export function Icon({ name }: Readonly<{ name: IconName }>) {
  return (
    <svg
      className="icon"
      viewBox="0 0 16 16"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

export function ToneBadge({
  tone,
  icon,
  label,
}: Readonly<{ tone: Tone; icon: IconName; label: string }>) {
  return (
    <span className="badge" data-tone={tone}>
      <Icon name={icon} />
      {label}
    </span>
  );
}

interface Props {
  status: Status;
  decision: DecisionKind | null;
}

export function StatusBadge({ status, decision }: Readonly<Props>) {
  const badge = badgeFor(status, decision);
  return <ToneBadge tone={badge.tone} icon={badge.icon} label={badge.label} />;
}
