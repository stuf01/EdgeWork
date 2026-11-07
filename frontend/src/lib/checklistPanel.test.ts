import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CHECKLIST_WRAP_PROPERTIES,
  CHECKLIST_WRAP_SELECTORS,
  PLAN_PANEL_COLUMN,
  checklistRowNeedsWrap,
  formatRuleComparison,
} from "./checklistPanel";

const css = readFileSync(resolve(__dirname, "../App.css"), "utf8");

function cssBlock(selector: string): string {
  const pattern = new RegExp(
    `${selector.replace(".", "\\.")}\\s*\\{([^}]+)\\}`,
    "m",
  );
  const match = css.match(pattern);
  expect(match, `missing CSS block for ${selector}`).toBeTruthy();
  return match?.[1] ?? "";
}

describe("chart plan checklist panel layout", () => {
  it("uses a wider plan-panel column so checklist rows have room", () => {
    expect(css).toContain(PLAN_PANEL_COLUMN);
    expect(css).toMatch(
      /\.ticker-layout\s*\{[^}]*minmax\(320px,\s*360px\)/s,
    );
  });

  it("wraps long checklist labels and values inside the panel", () => {
    for (const selector of CHECKLIST_WRAP_SELECTORS) {
      const block = cssBlock(selector);
      for (const prop of CHECKLIST_WRAP_PROPERTIES) {
        expect(block).toContain(prop);
      }
      expect(block).toContain("min-width: 0");
    }
    const values = cssBlock(".rule-values");
    expect(values).not.toMatch(/white-space:\s*nowrap/);
    expect(values).toMatch(/white-space:\s*normal/);
  });

  it("flags long rule rows that must wrap rather than overflow", () => {
    const longLabel = "Broken above yesterday's high with extra context";
    const comparison = formatRuleComparison("true", "==", "1");
    expect(checklistRowNeedsWrap(longLabel, comparison)).toBe(true);
    expect(checklistRowNeedsWrap("Gap %", "2 >= 2")).toBe(false);
  });
});
