/** Resolve lightweight-charts colors from the active CSS theme tokens. */

export type ChartThemeColors = {
  background: string;
  text: string;
  grid: string;
  border: string;
  accent: string;
  danger: string;
};

function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

export function readChartTheme(): ChartThemeColors {
  return {
    background: cssVar("--surface", "#ffffff"),
    text: cssVar("--muted", "#5b6b7c"),
    grid: cssVar("--line", "#eef2f6"),
    border: cssVar("--line", "#d7dee7"),
    accent: cssVar("--accent", "#0b6e4f"),
    danger: cssVar("--danger", "#a11d33"),
  };
}
