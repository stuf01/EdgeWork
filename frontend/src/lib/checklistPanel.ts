/** Layout contract for the ticker Chart Plan checklist panel. */

/** Side column width band used by `.ticker-layout` for the plan panel. */
export const PLAN_PANEL_COLUMN = "minmax(320px, 360px)";

/** Classes that must keep long checklist text inside the plan panel. */
export const CHECKLIST_WRAP_SELECTORS = [
  ".rule-label",
  ".rule-values",
] as const;

/** CSS properties that enforce wrapping instead of overflowing. */
export const CHECKLIST_WRAP_PROPERTIES = [
  "overflow-wrap: anywhere",
  "word-break: break-word",
] as const;

export function formatRuleComparison(
  actual: string | null | undefined,
  operator: string,
  threshold: string | null | undefined,
): string {
  return `${actual ?? "—"} ${operator} ${threshold ?? "—"}`;
}

/**
 * True when a checklist row is long enough that wrapping is required
 * to stay inside a typical plan-panel width.
 */
export function checklistRowNeedsWrap(
  label: string,
  comparison: string,
  maxChars = 36,
): boolean {
  return label.length > maxChars || comparison.length > maxChars;
}
