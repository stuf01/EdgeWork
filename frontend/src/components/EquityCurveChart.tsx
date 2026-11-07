import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import type { BacktestEquityPoint } from "../api";
import { readChartTheme } from "../lib/chartTheme";
import { useTheme } from "../theme/ThemeContext";

type EquityCurveChartProps = {
  points: BacktestEquityPoint[];
};

export default function EquityCurveChart({ points }: EquityCurveChartProps) {
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) {
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
      timeScale: { borderColor: colors.border },
    });
    chartRef.current = chart;

    const series = chart.addSeries(LineSeries, {
      color: colors.accent,
      lineWidth: 2,
      title: "Equity",
    });

    if (points.length === 0) {
      series.setData([]);
    } else {
      series.setData(
        points.map((point) => ({
          time: point.date as Time,
          value: Number(point.equity),
        })),
      );
      chart.timeScale().fitContent();
    }

    return () => {
      chartRef.current = null;
      chart.remove();
    };
  }, [points, theme]);

  return <div className="chart-host equity-curve-chart" ref={containerRef} />;
}
