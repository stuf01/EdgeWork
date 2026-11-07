import { useEffect, useRef } from "react";
import type { MutableRefObject } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { ChartTimeframe, IntradayBar, KeyLevels } from "../api";
import { readChartTheme } from "../lib/chartTheme";
import {
  applyPlacementClick,
  clampLongLevels,
  nextPlacementStep,
  snapPrice,
  type PlanLevels,
} from "../lib/planOnChart";
import { useTheme } from "../theme/ThemeContext";

type ChartProps = {
  bars: IntradayBar[];
  vwap: string[];
  levels: KeyLevels;
  timeframe: ChartTimeframe;
  showVwap: boolean;
  planMode?: boolean;
  planLevels?: PlanLevels;
  onPlanLevelsChange?: (levels: PlanLevels) => void;
};

const CHICAGO = "America/Chicago";
const HIT_PX = 6;

type PlanLineKey = "entry" | "stop" | "target";

function toChartTime(iso: string, timeframe: ChartTimeframe): Time {
  const date = new Date(iso);
  if (timeframe === "1Day") {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: CHICAGO,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date) as Time;
  }
  return Math.floor(date.getTime() / 1000) as Time;
}

function formatChicagoTick(time: Time, timeframe: ChartTimeframe): string {
  if (typeof time === "string") {
    const [year, month, day] = time.split("-");
    return `${month}/${day}/${year?.slice(2) ?? ""}`;
  }
  if (typeof time === "object") {
    return `${String(time.month).padStart(2, "0")}/${String(time.day).padStart(2, "0")}/${String(time.year).slice(2)}`;
  }
  const date = new Date(time * 1000);
  if (timeframe === "1Day") {
    return date.toLocaleDateString("en-US", {
      timeZone: CHICAGO,
      month: "short",
      day: "numeric",
    });
  }
  return date.toLocaleString("en-US", {
    timeZone: CHICAGO,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function Chart({
  bars,
  vwap,
  levels,
  timeframe,
  showVwap,
  planMode = false,
  planLevels = { entry: null, stop: null, target: null },
  onPlanLevelsChange,
}: ChartProps) {
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const planLinesRef = useRef<Partial<Record<PlanLineKey, IPriceLine>>>({});
  const planLevelsRef = useRef(planLevels);
  const planModeRef = useRef(planMode);
  const onChangeRef = useRef(onPlanLevelsChange);

  useEffect(() => {
    planLevelsRef.current = planLevels;
  }, [planLevels]);
  useEffect(() => {
    planModeRef.current = planMode;
  }, [planMode]);
  useEffect(() => {
    onChangeRef.current = onPlanLevelsChange;
  }, [onPlanLevelsChange]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || bars.length === 0) {
      return;
    }

    const colors = readChartTheme();
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: colors.background },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      rightPriceScale: { borderColor: colors.border },
      handleScroll: true,
      handleScale: true,
      timeScale: {
        borderColor: colors.border,
        timeVisible: timeframe !== "1Day",
        secondsVisible: false,
        tickMarkFormatter: (time: Time) => formatChicagoTick(time, timeframe),
      },
      localization: {
        timeFormatter: (time: Time) => formatChicagoTick(time, timeframe),
      },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: colors.accent,
      downColor: colors.danger,
      borderVisible: false,
      wickUpColor: colors.accent,
      wickDownColor: colors.danger,
    });
    seriesRef.current = candleSeries;
    candleSeries.setData(
      bars.map((bar) => ({
        time: toChartTime(bar.timestamp, timeframe),
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
      })),
    );

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(
      bars.map((bar) => {
        const up = Number(bar.close) >= Number(bar.open);
        return {
          time: toChartTime(bar.timestamp, timeframe),
          value: bar.volume,
          color: up ? `${colors.accent}59` : `${colors.danger}59`,
        };
      }),
    );

    if (showVwap && vwap.length > 0) {
      const vwapSeries = chart.addSeries(LineSeries, {
        color: "#1d4ed8",
        lineWidth: 2,
        title: "VWAP",
      });
      const vwapPoints = bars
        .map((bar, index) => {
          const value = vwap[index];
          if (value === undefined) {
            return null;
          }
          return {
            time: toChartTime(bar.timestamp, timeframe),
            value: Number(value),
          };
        })
        .filter(
          (point): point is { time: Time; value: number } => point !== null,
        );
      vwapSeries.setData(vwapPoints);
    }

    const lineSpecs: Array<{
      value: string | null;
      color: string;
      title: string;
    }> = [
      { value: levels.prev_day_high, color: "#7c3aed", title: "PDH" },
      { value: levels.prev_day_low, color: "#c2410c", title: "PDL" },
      { value: levels.today_open, color: "#0f766e", title: "Open" },
    ];
    for (const spec of lineSpecs) {
      if (spec.value == null) {
        continue;
      }
      candleSeries.createPriceLine({
        price: Number(spec.value),
        color: spec.color,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: spec.title,
      });
    }

    // Restore any active plan lines after chart rebuild.
    syncPlanLines(candleSeries, planLevelsRef.current, planLinesRef);

    chart.timeScale().fitContent();

    let dragging: PlanLineKey | null = null;
    let suppressClick = false;

    const yFromEvent = (event: MouseEvent): number | null => {
      const rect = el.getBoundingClientRect();
      return event.clientY - rect.top;
    };

    const hitTest = (y: number): PlanLineKey | null => {
      const series = seriesRef.current;
      const current = planLevelsRef.current;
      if (!series) {
        return null;
      }
      const keys: PlanLineKey[] = ["entry", "stop", "target"];
      for (const key of keys) {
        const price = current[key];
        if (price == null) {
          continue;
        }
        const coord = series.priceToCoordinate(price);
        if (coord == null) {
          continue;
        }
        if (Math.abs(coord - y) <= HIT_PX) {
          return key;
        }
      }
      return null;
    };

    const setInteraction = (enabled: boolean) => {
      chart.applyOptions({
        handleScroll: enabled,
        handleScale: enabled,
      });
    };

    const onMove = (event: MouseEvent) => {
      if (!planModeRef.current) {
        el.style.cursor = "default";
        return;
      }
      const y = yFromEvent(event);
      if (y == null) {
        return;
      }
      if (dragging) {
        const series = seriesRef.current;
        if (!series) {
          return;
        }
        const price = series.coordinateToPrice(y);
        if (price == null) {
          return;
        }
        const snapped = snapPrice(price);
        const next = clampLongLevels(
          { ...planLevelsRef.current, [dragging]: snapped },
          dragging,
        );
        planLevelsRef.current = next;
        syncPlanLines(series, next, planLinesRef);
        onChangeRef.current?.(next);
        el.style.cursor = "ns-resize";
        return;
      }
      el.style.cursor = hitTest(y) ? "ns-resize" : "crosshair";
    };

    const onDown = (event: MouseEvent) => {
      if (!planModeRef.current || event.button !== 0) {
        return;
      }
      const y = yFromEvent(event);
      if (y == null) {
        return;
      }
      const hit = hitTest(y);
      if (hit && nextPlacementStep(planLevelsRef.current) === "done") {
        dragging = hit;
        suppressClick = true;
        setInteraction(false);
        el.style.cursor = "ns-resize";
        event.preventDefault();
      }
    };

    const onUp = () => {
      if (dragging) {
        dragging = null;
        setInteraction(true);
        window.setTimeout(() => {
          suppressClick = false;
        }, 0);
      }
    };

    const onClick = (event: MouseEvent) => {
      if (!planModeRef.current || suppressClick) {
        return;
      }
      if (nextPlacementStep(planLevelsRef.current) === "done") {
        return;
      }
      const series = seriesRef.current;
      const y = yFromEvent(event);
      if (!series || y == null) {
        return;
      }
      const price = series.coordinateToPrice(y);
      if (price == null) {
        return;
      }
      const next = applyPlacementClick(planLevelsRef.current, price);
      planLevelsRef.current = next;
      syncPlanLines(series, next, planLinesRef);
      onChangeRef.current?.(next);
    };

    el.addEventListener("mousemove", onMove);
    el.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    el.addEventListener("click", onClick);

    return () => {
      el.removeEventListener("mousemove", onMove);
      el.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      el.removeEventListener("click", onClick);
      planLinesRef.current = {};
      seriesRef.current = null;
      chartRef.current = null;
      chart.remove();
    };
  }, [bars, vwap, levels, timeframe, showVwap, theme]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) {
      return;
    }
    if (!planMode) {
      clearPlanLines(series, planLinesRef);
      return;
    }
    syncPlanLines(series, planLevels, planLinesRef);
  }, [planMode, planLevels]);

  return (
    <div
      className={planMode ? "chart-host plan-mode" : "chart-host"}
      ref={containerRef}
    />
  );
}

function clearPlanLines(
  series: ISeriesApi<"Candlestick">,
  planLinesRef: MutableRefObject<Partial<Record<PlanLineKey, IPriceLine>>>,
) {
  for (const key of Object.keys(planLinesRef.current) as PlanLineKey[]) {
    const line = planLinesRef.current[key];
    if (line) {
      series.removePriceLine(line);
    }
  }
  planLinesRef.current = {};
}

function syncPlanLines(
  series: ISeriesApi<"Candlestick">,
  levels: PlanLevels,
  planLinesRef: MutableRefObject<Partial<Record<PlanLineKey, IPriceLine>>>,
) {
  const specs: Array<{ key: PlanLineKey; color: string; title: string }> = [
    { key: "entry", color: "#2563eb", title: "Entry" },
    { key: "stop", color: "#a11d33", title: "Stop" },
    { key: "target", color: "#0b6e4f", title: "Target" },
  ];
  for (const spec of specs) {
    const price = levels[spec.key];
    const existing = planLinesRef.current[spec.key];
    if (price == null) {
      if (existing) {
        series.removePriceLine(existing);
        delete planLinesRef.current[spec.key];
      }
      continue;
    }
    const label = `${spec.title} ${price.toFixed(2)}`;
    if (existing) {
      existing.applyOptions({ price, title: label });
    } else {
      planLinesRef.current[spec.key] = series.createPriceLine({
        price,
        color: spec.color,
        lineWidth: 2,
        lineStyle: 0,
        axisLabelVisible: true,
        title: label,
      });
    }
  }
}
