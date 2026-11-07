/** Shared Planner / chart-plan account risk settings in localStorage. */

export const ACCOUNT_SIZE_KEY = "edgework.accountSize";
export const RISK_PERCENT_KEY = "edgework.riskPercent";

export function readAccountSize(defaultValue = ""): string {
  try {
    return window.localStorage.getItem(ACCOUNT_SIZE_KEY) ?? defaultValue;
  } catch {
    return defaultValue;
  }
}

export function readRiskPercent(defaultValue = "1"): string {
  try {
    return window.localStorage.getItem(RISK_PERCENT_KEY) ?? defaultValue;
  } catch {
    return defaultValue;
  }
}

export function writeAccountSize(value: string): void {
  try {
    window.localStorage.setItem(ACCOUNT_SIZE_KEY, value);
  } catch {
    // ignore
  }
}

export function writeRiskPercent(value: string): void {
  try {
    window.localStorage.setItem(RISK_PERCENT_KEY, value);
  } catch {
    // ignore
  }
}
