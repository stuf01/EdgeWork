/** Pure helpers for interactive chart trade planning (long side only). */

export type PlanLevels = {
  entry: number | null;
  stop: number | null;
  target: number | null;
};

export type PlacementStep = "entry" | "stop" | "target" | "done";

export type PreviewPlan = {
  max_risk_dollars: number;
  risk_per_share: number;
  shares: number;
  actual_risk_dollars: number;
  reward_per_share: number;
  potential_profit: number;
  risk_reward_ratio: number;
  position_cost: number;
  exceeds_account: boolean;
};

export type PreviewResult =
  | { ok: true; plan: PreviewPlan }
  | { ok: false; error: string };

export function snapPrice(price: number, decimals = 2): number {
  if (!Number.isFinite(price)) {
    return 0;
  }
  const factor = 10 ** decimals;
  return Math.round(price * factor) / factor;
}

export function nextPlacementStep(levels: PlanLevels): PlacementStep {
  if (levels.entry == null) {
    return "entry";
  }
  if (levels.stop == null) {
    return "stop";
  }
  if (levels.target == null) {
    return "target";
  }
  return "done";
}

export function placementInstruction(step: PlacementStep): string {
  switch (step) {
    case "entry":
      return "Click to set your entry";
    case "stop":
      return "Click to set your stop (below entry)";
    case "target":
      return "Click to set your target (above entry)";
    default:
      return "Drag lines to adjust, or reset to place again";
  }
}

/** Apply a chart click during the placement sequence (snapped). */
export function applyPlacementClick(
  levels: PlanLevels,
  rawPrice: number,
  tick = 0.01,
): PlanLevels {
  const price = snapPrice(rawPrice);
  const step = nextPlacementStep(levels);
  if (step === "entry") {
    return { entry: price, stop: null, target: null };
  }
  if (step === "stop") {
    const entry = levels.entry;
    if (entry == null) {
      return levels;
    }
    // Longs require stop below entry; nudge if the click landed on/above.
    const stop = price < entry ? price : snapPrice(entry - tick);
    return { ...levels, stop };
  }
  if (step === "target") {
    const entry = levels.entry;
    if (entry == null) {
      return levels;
    }
    // Longs require target above entry; nudge if the click landed on/below.
    const target = price > entry ? price : snapPrice(entry + tick);
    return { ...levels, target };
  }
  return levels;
}

export type PlacementVerdict = "good" | "fair" | "poor" | "invalid";

export type PlacementAssessment = {
  verdict: PlacementVerdict;
  headline: string;
  reasons: string[];
};

function moneyLabel(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Explain whether the long Entry / Stop / Target placement looks workable
 * and why — including the common “$0 potential profit” case (0 shares).
 */
export function assessPlacement(
  levels: PlanLevels,
  accountSize: number,
  riskPercent: number,
  lastPrice?: number | null,
): PlacementAssessment | null {
  const { entry, stop, target } = levels;
  if (entry == null || stop == null || target == null) {
    return null;
  }

  const reasons: string[] = [];

  if (!(entry > 0 && stop > 0 && target > 0)) {
    return {
      verdict: "invalid",
      headline: "Prices must be greater than zero",
      reasons: ["Re-place entry, stop, and target on the chart."],
    };
  }

  if (!(stop < entry)) {
    return {
      verdict: "invalid",
      headline: "Stop is not below entry",
      reasons: [
        "This planner is long-only: stop must sit under entry so risk per share is positive.",
        `Entry ${moneyLabel(entry)} · Stop ${moneyLabel(stop)}.`,
      ],
    };
  }

  if (!(entry < target)) {
    return {
      verdict: "invalid",
      headline: "Target is not above entry",
      reasons: [
        "For a long, target must sit above entry so there is upside to capture.",
        `Entry ${moneyLabel(entry)} · Target ${moneyLabel(target)}.`,
      ],
    };
  }

  if (!(accountSize > 0) || !(riskPercent > 0) || riskPercent > 100) {
    return {
      verdict: "invalid",
      headline: "Account size or risk % is invalid",
      reasons: [
        "Set a positive account size and a risk percent between 0 and 100 in the plan panel.",
      ],
    };
  }

  const preview = previewPlan(accountSize, riskPercent, entry, stop, target);
  if (!preview.ok) {
    return {
      verdict: "invalid",
      headline: "Cannot size this plan",
      reasons: [preview.error],
    };
  }

  const plan = preview.plan;
  const stopPct = ((entry - stop) / entry) * 100;
  const targetPct = ((target - entry) / entry) * 100;

  if (plan.shares <= 0) {
    reasons.push(
      `Potential profit is $0 because risk per share (${moneyLabel(plan.risk_per_share)}) is larger than your max risk budget (${moneyLabel(plan.max_risk_dollars)}), so share size floors to 0.`,
    );
    reasons.push(
      "Tighten the stop toward entry, raise account size, or increase risk % so at least 1 share fits the budget.",
    );
  }

  if (plan.risk_reward_ratio < 1) {
    reasons.push(
      `Reward (${moneyLabel(plan.reward_per_share)}/share) is smaller than risk (${moneyLabel(plan.risk_per_share)}/share) — R:R ${plan.risk_reward_ratio.toFixed(2)}:1. Move the target farther or the stop closer.`,
    );
  } else if (plan.risk_reward_ratio < 2) {
    reasons.push(
      `R:R is ${plan.risk_reward_ratio.toFixed(2)}:1 (below the usual 2:1 guideline). Consider a higher target or a tighter stop.`,
    );
  }

  if (stopPct < 0.15) {
    reasons.push(
      `Stop is only ${stopPct.toFixed(2)}% below entry — normal noise can stop you out. Give the stop a bit more room unless that is intentional.`,
    );
  } else if (stopPct > 8) {
    reasons.push(
      `Stop is ${stopPct.toFixed(1)}% below entry — wide risk per share shrinks (or zeros) position size.`,
    );
  }

  if (plan.exceeds_account && plan.shares > 0) {
    reasons.push(
      `Position cost (${moneyLabel(plan.position_cost)}) exceeds account size (${moneyLabel(accountSize)}). Lower risk %, widen the stop, or raise account size.`,
    );
  }

  if (
    lastPrice != null &&
    Number.isFinite(lastPrice) &&
    lastPrice > 0 &&
    entry > lastPrice * 1.03
  ) {
    reasons.push(
      `Entry is ~${(((entry - lastPrice) / lastPrice) * 100).toFixed(1)}% above the last price — you may be chasing; confirm the breakout level is intentional.`,
    );
  }

  if (plan.shares > 0 && plan.risk_reward_ratio >= 2 && !plan.exceeds_account) {
    reasons.unshift(
      `Workable long: ${plan.shares} shares, R:R ${plan.risk_reward_ratio.toFixed(2)}:1, potential profit ${moneyLabel(plan.potential_profit)} vs risk ${moneyLabel(plan.actual_risk_dollars)} (stop ${stopPct.toFixed(2)}% / target ${targetPct.toFixed(2)}%).`,
    );
  }

  let verdict: PlacementVerdict = "good";
  if (plan.shares <= 0 || plan.risk_reward_ratio < 1) {
    verdict = "poor";
  } else if (
    plan.risk_reward_ratio < 2 ||
    plan.exceeds_account ||
    stopPct < 0.15 ||
    stopPct > 8 ||
    (lastPrice != null &&
      Number.isFinite(lastPrice) &&
      lastPrice > 0 &&
      entry > lastPrice * 1.03)
  ) {
    verdict = "fair";
  }

  const headline =
    verdict === "good"
      ? "Good placement"
      : verdict === "fair"
        ? "Okay placement — review the notes"
        : "Weak placement";

  if (reasons.length === 0) {
    reasons.push("Levels are ordered correctly for a long (stop < entry < target).");
  }

  return { verdict, headline, reasons };
}

/**
 * Enforce long-side ordering when dragging: stop < entry < target.
 * The dragged line is preferred; the others shift if needed by a tick.
 */
export function clampLongLevels(
  levels: PlanLevels,
  dragged: keyof PlanLevels,
  tick = 0.01,
): PlanLevels {
  let entry = levels.entry;
  let stop = levels.stop;
  let target = levels.target;
  if (entry == null) {
    return levels;
  }
  entry = snapPrice(entry);
  if (stop != null) {
    stop = snapPrice(stop);
  }
  if (target != null) {
    target = snapPrice(target);
  }

  if (dragged === "entry") {
    if (stop != null && !(stop < entry)) {
      stop = snapPrice(entry - tick);
    }
    if (target != null && !(entry < target)) {
      target = snapPrice(entry + tick);
    }
  } else if (dragged === "stop" && stop != null) {
    if (!(stop < entry)) {
      stop = snapPrice(entry - tick);
    }
  } else if (dragged === "target" && target != null) {
    if (!(entry < target)) {
      target = snapPrice(entry + tick);
    }
  }

  // Final safety if all three present.
  if (stop != null && target != null && !(stop < entry && entry < target)) {
    if (dragged === "stop") {
      stop = snapPrice(Math.min(stop, entry - tick));
    } else if (dragged === "target") {
      target = snapPrice(Math.max(target, entry + tick));
    } else {
      stop = snapPrice(Math.min(stop, entry - tick));
      target = snapPrice(Math.max(target, entry + tick));
    }
  }

  return { entry, stop, target };
}

/** Client-side preview matching backend planner formulas (long only). */
export function previewPlan(
  accountSize: number,
  riskPercent: number,
  entry: number,
  stop: number,
  target: number,
): PreviewResult {
  if (!(accountSize > 0)) {
    return { ok: false, error: "account_size must be greater than 0" };
  }
  if (!(riskPercent > 0)) {
    return { ok: false, error: "risk_percent must be greater than 0" };
  }
  if (riskPercent > 100) {
    return { ok: false, error: "risk_percent must be less than or equal to 100" };
  }
  if (!(entry > 0 && stop > 0 && target > 0)) {
    return { ok: false, error: "prices must be greater than 0" };
  }
  if (!(stop < entry && entry < target)) {
    return { ok: false, error: "prices must satisfy stop < entry < target" };
  }

  const maxRisk = (accountSize * riskPercent) / 100;
  const riskPerShare = entry - stop;
  const shares = Math.floor(maxRisk / riskPerShare);
  const actualRisk = shares * riskPerShare;
  const rewardPerShare = target - entry;
  const potentialProfit = shares * rewardPerShare;
  const riskReward = rewardPerShare / riskPerShare;
  const positionCost = shares * entry;

  return {
    ok: true,
    plan: {
      max_risk_dollars: maxRisk,
      risk_per_share: riskPerShare,
      shares,
      actual_risk_dollars: actualRisk,
      reward_per_share: rewardPerShare,
      potential_profit: potentialProfit,
      risk_reward_ratio: riskReward,
      position_cost: positionCost,
      exceeds_account: positionCost > accountSize,
    },
  };
}

export function emptyPlanLevels(): PlanLevels {
  return { entry: null, stop: null, target: null };
}
