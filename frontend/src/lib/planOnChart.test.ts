import { describe, expect, it } from "vitest";
import {
  applyPlacementClick,
  assessPlacement,
  clampLongLevels,
  emptyPlanLevels,
  nextPlacementStep,
  previewPlan,
  snapPrice,
} from "./planOnChart";

describe("snapPrice", () => {
  it("rounds to two decimals", () => {
    expect(snapPrice(10.126)).toBe(10.13);
    expect(snapPrice(10.124)).toBe(10.12);
    expect(snapPrice(10)).toBe(10);
  });
});

describe("placement sequence", () => {
  it("walks entry -> stop -> target -> done", () => {
    let levels = emptyPlanLevels();
    expect(nextPlacementStep(levels)).toBe("entry");
    levels = applyPlacementClick(levels, 10.126);
    expect(levels.entry).toBe(10.13);
    expect(nextPlacementStep(levels)).toBe("stop");
    levels = applyPlacementClick(levels, 9.5);
    expect(levels.stop).toBe(9.5);
    expect(nextPlacementStep(levels)).toBe("target");
    levels = applyPlacementClick(levels, 12);
    expect(levels.target).toBe(12);
    expect(nextPlacementStep(levels)).toBe("done");
    expect(applyPlacementClick(levels, 11)).toEqual(levels);
  });
});

describe("clampLongLevels", () => {
  it("keeps stop below entry when dragging stop up", () => {
    const clamped = clampLongLevels(
      { entry: 10, stop: 10.5, target: 12 },
      "stop",
    );
    expect(clamped.stop).toBe(9.99);
    expect(clamped.entry).toBe(10);
  });

  it("keeps target above entry when dragging target down", () => {
    const clamped = clampLongLevels(
      { entry: 10, stop: 9, target: 9.5 },
      "target",
    );
    expect(clamped.target).toBe(10.01);
  });

  it("shifts target above entry when dragging entry through target", () => {
    const clamped = clampLongLevels(
      { entry: 11, stop: 10, target: 10.5 },
      "entry",
    );
    expect(clamped.entry).toBe(11);
    expect(clamped.stop).toBe(10);
    expect(clamped.target).toBe(11.01);
  });

  it("shifts stop below entry when dragging entry through stop", () => {
    const clamped = clampLongLevels(
      { entry: 9, stop: 10, target: 12 },
      "entry",
    );
    expect(clamped.entry).toBe(9);
    expect(clamped.stop).toBe(8.99);
    expect(clamped.target).toBe(12);
  });
});

describe("previewPlan", () => {
  it("matches the required backend happy path", () => {
    const result = previewPlan(10000, 1, 40, 39.5, 41.5);
    expect(result.ok).toBe(true);
    if (!result.ok) {
      return;
    }
    expect(result.plan.max_risk_dollars).toBe(100);
    expect(result.plan.risk_per_share).toBe(0.5);
    expect(result.plan.shares).toBe(200);
    expect(result.plan.reward_per_share).toBe(1.5);
    expect(result.plan.risk_reward_ratio).toBe(3);
    expect(result.plan.exceeds_account).toBe(false);
  });

  it("rejects invalid stop/target ordering", () => {
    const result = previewPlan(10000, 1, 40, 40.5, 41.5);
    expect(result.ok).toBe(false);
    if (result.ok) {
      return;
    }
    expect(result.error).toMatch(/stop < entry < target/);
  });

  it("floors shares", () => {
    const result = previewPlan(10000, 1, 10, 9.67, 11);
    expect(result.ok).toBe(true);
    if (!result.ok) {
      return;
    }
    expect(result.plan.shares).toBe(303);
  });
});

describe("applyPlacementClick long clamping", () => {
  it("nudges stop below entry when click is above", () => {
    const levels = applyPlacementClick(
      { entry: 10, stop: null, target: null },
      10.5,
    );
    expect(levels.stop).toBe(9.99);
  });

  it("nudges target above entry when click is below", () => {
    const levels = applyPlacementClick(
      { entry: 10, stop: 9.5, target: null },
      9.8,
    );
    expect(levels.target).toBe(10.01);
  });
});

describe("assessPlacement", () => {
  it("flags zero profit when shares floor to 0", () => {
    // Max risk $100; risk/share $150 → floor(100/150) = 0 shares.
    const review = assessPlacement(
      { entry: 200, stop: 50, target: 250 },
      10000,
      1,
    );
    expect(review).not.toBeNull();
    expect(review?.verdict).toBe("poor");
    expect(review?.reasons.join(" ")).toMatch(
      /floors to 0|0 shares|Potential profit is \$0/i,
    );
  });

  it("marks a solid 2:1 long as good", () => {
    const review = assessPlacement(
      { entry: 40, stop: 39.5, target: 41.5 },
      10000,
      1,
      39.9,
    );
    expect(review?.verdict).toBe("good");
    expect(review?.headline).toMatch(/Good/i);
  });

  it("marks sub-2 R:R as fair", () => {
    // Risk $1 / reward $1.50 → 1.5:1 (below 2:1, still >= 1:1).
    const review = assessPlacement(
      { entry: 40, stop: 39, target: 41.5 },
      10000,
      1,
    );
    expect(review?.verdict).toBe("fair");
    expect(review?.reasons.join(" ")).toMatch(/2:1/);
  });
});
