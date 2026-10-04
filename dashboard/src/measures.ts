import type { Measures } from "./api";
import { duration, modelCost, money, percent } from "./format";

// The scoreboard's measures, in order, each with how it's shown, or null
// while it can't be known yet.
export const MEASURES: {
  label: string;
  show: (measures: Measures) => string | null;
}[] = [
  { label: "Decision accuracy", show: (m) => percent(m.decision_accuracy) },
  { label: "Accuracy", show: (m) => percent(m.accuracy) },
  { label: "Cost of mistakes", show: (m) => money(m.cost_of_mistakes) },
  { label: "Straight-through", show: (m) => percent(m.straight_through) },
  {
    label: "Model cost per claim",
    show: (m) => modelCost(m.model_cost_per_claim),
  },
  { label: "Time per claim", show: (m) => duration(m.seconds_per_claim) },
  {
    label: "Run time",
    show: (m) => (m.run_seconds === null ? null : duration(m.run_seconds)),
  },
];
