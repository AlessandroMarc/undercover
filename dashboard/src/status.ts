import type { DecisionKind, RunStatus, Status, TodoStatus } from "./types";

export type Tone = "green" | "marigold" | "coral" | "cerulean" | "raspberry";
export type IconName = "check" | "clock" | "question" | "dot" | "flag" | "pen";

export interface Badge {
  label: string;
  tone: Tone;
  icon: IconName;
}

const DECISIONS: Record<DecisionKind, Badge> = {
  approve: { label: "Approved", tone: "green", icon: "check" },
  decline: { label: "Declined", tone: "raspberry", icon: "flag" },
  refer: { label: "Referred", tone: "coral", icon: "question" },
};

const STATES: Record<Exclude<Status, "decided">, Badge> = {
  waiting: { label: "Waiting", tone: "cerulean", icon: "dot" },
  in_progress: { label: "In progress", tone: "marigold", icon: "clock" },
  awaiting_signoff: { label: "Needs sign-off", tone: "coral", icon: "pen" },
  needs_handler: {
    label: "Left for a handler",
    tone: "coral",
    icon: "question",
  },
};

export const TODOS: Record<TodoStatus, Badge> = {
  todo: { label: "To do", tone: "cerulean", icon: "dot" },
  in_progress: { label: "In progress", tone: "marigold", icon: "clock" },
  done: { label: "Done", tone: "green", icon: "check" },
  left_for_handler: {
    label: "Left for a handler",
    tone: "coral",
    icon: "question",
  },
};

export const RUNS: Record<RunStatus, Badge> = {
  running: { label: "Running", tone: "marigold", icon: "clock" },
  finished: { label: "Finished", tone: "green", icon: "check" },
  failed: { label: "Failed", tone: "raspberry", icon: "flag" },
};

export function badgeFor(status: Status, decision: DecisionKind | null): Badge {
  if (status === "decided" && decision) return DECISIONS[decision];
  if (status === "decided") return DECISIONS.approve;
  return STATES[status];
}
